"""
Unit tests for the src/ modules.

These cover the pure logic — data loading, categorization normalization, the
feedback loop, ticket ID allocation and email formatting. No network calls:
Groq, Gemini and MongoDB are all mocked.
"""

import datetime
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.data_loader import DataLoader
from src.response_generator import ResponseGenerator, FeedbackLoop


# ── DATA LOADER ───────────────────────────────────────────────────────────────

CSV_WITH_CATEGORY = (
    "instruction,response,category\n"
    "How do I reset my password?,Click forgot password.,Account Management\n"
    "Where is my order?,Track it in your dashboard.,Shipping & Delivery\n"
)

CSV_WITHOUT_CATEGORY = (
    "instruction,response\n"
    "How do I reset my password?,Click forgot password.\n"
)


def _write_csv(tmp_path, content, name="tickets.csv"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


class TestDataLoader:
    def test_load_data_returns_rows(self, tmp_path):
        loader = DataLoader(_write_csv(tmp_path, CSV_WITH_CATEGORY))
        assert len(loader.load_data()) == 2

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            DataLoader("does/not/exist.csv").load_data()

    def test_documents_carry_category_from_csv(self, tmp_path):
        loader = DataLoader(_write_csv(tmp_path, CSV_WITH_CATEGORY))
        loader.load_data()
        docs = loader.create_documents()
        assert [d["category"] for d in docs] == [
            "Account Management",
            "Shipping & Delivery",
        ]

    def test_documents_default_category_when_column_absent(self, tmp_path):
        loader = DataLoader(_write_csv(tmp_path, CSV_WITHOUT_CATEGORY))
        loader.load_data()
        docs = loader.create_documents()
        assert docs[0]["category"] == "General"

    def test_combined_text_contains_both_sides(self, tmp_path):
        loader = DataLoader(_write_csv(tmp_path, CSV_WITH_CATEGORY))
        loader.load_data()
        doc = loader.create_documents()[0]
        assert "How do I reset my password?" in doc["combined_text"]
        assert "Click forgot password." in doc["combined_text"]

    def test_missing_required_column_raises(self, tmp_path):
        path = _write_csv(tmp_path, "question,answer\na,b\n")
        loader = DataLoader(path)
        loader.load_data()
        with pytest.raises(ValueError, match="missing required column"):
            loader.create_documents()

    def test_preprocess_removes_duplicates(self, tmp_path):
        dupes = CSV_WITHOUT_CATEGORY + "How do I reset my password?,Click forgot password.\n"
        loader = DataLoader(_write_csv(tmp_path, dupes))
        loader.load_data()
        assert len(loader.preprocess_data()) == 1

    def test_split_data_proportions(self, tmp_path):
        rows = "instruction,response\n" + "".join(
            f"question {i},answer {i}\n" for i in range(10)
        )
        loader = DataLoader(_write_csv(tmp_path, rows))
        loader.load_data()
        train, test = loader.split_data(test_size=0.2)
        assert (len(train), len(test)) == (8, 2)


# ── CATEGORIZATION ────────────────────────────────────────────────────────────

def _generator(llm_reply="{}"):
    with patch("src.response_generator.GroqClient") as mock_client:
        mock_client.return_value.generate.return_value = llm_reply
        gen = ResponseGenerator(api_key="test-key")
    return gen


class TestCategorization:
    def test_parses_clean_json(self):
        gen = _generator(json.dumps({
            "category": "Billing",
            "priority": "high",
            "sentiment": "negative",
            "summary": "Customer was double charged.",
        }))
        result = gen.categorize_ticket("I was charged twice")
        assert result == {
            "category": "Billing",
            "priority": "high",
            "sentiment": "negative",
            "summary": "Customer was double charged.",
        }

    def test_strips_markdown_code_fence(self):
        gen = _generator(
            '```json\n{"category":"Billing","priority":"low",'
            '"sentiment":"neutral","summary":"s"}\n```'
        )
        assert gen.categorize_ticket("q")["category"] == "Billing"

    def test_extracts_json_wrapped_in_prose(self):
        gen = _generator(
            'Sure! Here you go: {"category":"Billing","priority":"low",'
            '"sentiment":"neutral","summary":"s"} Hope that helps.'
        )
        assert gen.categorize_ticket("q")["category"] == "Billing"

    def test_unknown_category_falls_back_to_general_inquiry(self):
        gen = _generator(json.dumps({
            "category": "Interdimensional Portals",
            "priority": "low",
            "sentiment": "neutral",
            "summary": "s",
        }))
        assert gen.categorize_ticket("q")["category"] == "General Inquiry"

    def test_category_match_is_case_insensitive(self):
        gen = _generator(json.dumps({
            "category": "billing",
            "priority": "low",
            "sentiment": "neutral",
            "summary": "s",
        }))
        assert gen.categorize_ticket("q")["category"] == "Billing"

    def test_verbose_priority_is_normalized(self):
        gen = _generator(json.dumps({
            "category": "Billing",
            "priority": "Urgent Priority",
            "sentiment": "neutral",
            "summary": "s",
        }))
        assert gen.categorize_ticket("q")["priority"] == "urgent"

    def test_priority_is_always_a_known_sla_key(self):
        gen = _generator(json.dumps({
            "category": "Billing",
            "priority": "catastrophic",
            "sentiment": "neutral",
            "summary": "s",
        }))
        assert gen.categorize_ticket("q")["priority"] in Config.PRIORITY_SLA

    def test_unparseable_output_falls_back(self):
        gen = _generator("I'm sorry, I cannot do that.")
        result = gen.categorize_ticket("my invoice is wrong")
        assert result["category"] == "General Inquiry"
        assert result["priority"] == "medium"
        assert result["summary"] == "my invoice is wrong"

    def test_llm_failure_falls_back(self):
        gen = _generator()
        gen.llm.generate.side_effect = RuntimeError("Groq API error")
        assert gen.categorize_ticket("q")["category"] == "General Inquiry"

    def test_non_dict_json_falls_back(self):
        gen = _generator('["billing"]')
        assert gen.categorize_ticket("q")["category"] == "General Inquiry"

    def test_missing_summary_falls_back_to_query(self):
        gen = _generator(json.dumps({"category": "Billing", "priority": "low"}))
        assert gen.categorize_ticket("broken invoice")["summary"] == "broken invoice"


# ── FEEDBACK LOOP ─────────────────────────────────────────────────────────────

class TestFeedbackLoop:
    def _loop(self, db=None):
        gen = MagicMock()
        gen.improve_response.return_value = "A much better answer."
        return FeedbackLoop(gen, db_client=db), gen

    def test_returns_improved_response(self):
        loop, _ = self._loop()
        result = loop.submit_feedback("q", "meh answer", "too vague", rating=2)
        assert result["improved_response"] == "A much better answer."

    def test_falls_back_to_memory_without_db(self):
        loop, _ = self._loop()
        loop.submit_feedback("q", "orig", "fb")
        assert len(loop.get_feedback_history()) == 1

    def test_persists_to_db_when_available(self):
        db = MagicMock()
        db.save_feedback.return_value = "abc123"
        loop, _ = self._loop(db)
        assert loop.submit_feedback("q", "orig", "fb")["feedback_id"] == "abc123"
        db.save_feedback.assert_called_once()

    def test_db_failure_keeps_record_in_memory(self):
        db = MagicMock()
        db.save_feedback.side_effect = RuntimeError("mongo down")
        db.get_all_feedback.side_effect = RuntimeError("mongo down")
        loop, _ = self._loop(db)
        loop.submit_feedback("q", "orig", "fb")
        assert len(loop.get_feedback_history()) == 1

    def test_export_writes_json_file(self, tmp_path):
        loop, _ = self._loop()
        loop.submit_feedback("q", "orig", "fb", rating=4)
        path = loop.export_feedback(str(tmp_path / "out.json"))

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data[0]["feedback"] == "fb"
        assert data[0]["rating"] == 4

    def test_export_serialises_datetimes(self, tmp_path):
        db = MagicMock()
        db.get_all_feedback.return_value = [
            {"feedback": "fb", "created_at": datetime.datetime(2026, 4, 20, 12, 0)}
        ]
        loop, _ = self._loop(db)
        path = loop.export_feedback(str(tmp_path / "out.json"))

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data[0]["created_at"].startswith("2026-04-20")


# ── RESPONSE GENERATION ───────────────────────────────────────────────────────

class TestResponseGeneration:
    def test_uses_rag_context_when_available(self):
        gen = _generator("answer")
        rag = MagicMock()
        rag.is_initialized = True
        rag.get_context.return_value = "PAST TICKET CONTEXT"
        gen.set_rag_engine(rag)

        gen.generate_response("why is my bill wrong")

        rag.get_context.assert_called_once()
        assert "PAST TICKET CONTEXT" in gen.llm.generate.call_args[0][0]

    def test_skips_rag_when_disabled(self):
        gen = _generator("answer")
        rag = MagicMock()
        rag.is_initialized = True
        gen.set_rag_engine(rag)

        gen.generate_response("q", use_rag=False)

        rag.get_context.assert_not_called()

    def test_llm_failure_returns_graceful_message(self):
        gen = _generator()
        gen.llm.generate.side_effect = RuntimeError("Groq down")
        assert "apologize" in gen.generate_response("q").lower()

    def test_self_help_survives_llm_failure(self):
        gen = _generator()
        gen.llm.generate.side_effect = RuntimeError("Groq down")
        assert "support" in gen.generate_self_help("q").lower()

    def test_multiple_responses_vary_temperature(self):
        gen = _generator("candidate")
        candidates = gen.generate_multiple_responses("q", num_candidates=3)
        assert len(candidates) == 3
        assert len({c["temperature"] for c in candidates}) == 3

    def test_improve_response_falls_back_to_original(self):
        gen = _generator()
        gen.llm.generate.side_effect = RuntimeError("Groq down")
        assert gen.improve_response("original text", "fix it") == "original text"


# ── MONGO CLIENT (no server required) ─────────────────────────────────────────

class TestMongoClient:
    def _client(self):
        from src.db import MongoDBClient
        client = MongoDBClient(uri="mongodb://localhost:27017", db_name="test_db")
        client._db = MagicMock()
        return client

    def test_redacts_credentials_in_uri(self):
        from src.db import _redact_uri
        redacted = _redact_uri("mongodb+srv://user:secret@cluster.mongodb.net/db")
        assert "secret" not in redacted and "user" not in redacted
        assert redacted.startswith("mongodb+srv://<credentials>@")

    def test_redact_handles_uri_without_credentials(self):
        from src.db import _redact_uri
        assert _redact_uri("mongodb://localhost:27017") == "mongodb://localhost:27017"

    def test_ticket_id_uses_atomic_counter(self):
        client = self._client()
        client._db["counters"].find_one_and_update.return_value = {"seq": 7}
        assert client._generate_ticket_id().endswith("-0007")

    def test_save_ticket_returns_generated_id(self):
        client = self._client()
        client._db["counters"].find_one_and_update.return_value = {"seq": 1}
        ticket_id = client.save_ticket({"user_name": "A", "user_email": "a@b.com"})
        assert ticket_id.startswith("TKT-") and ticket_id.endswith("-0001")
        client._db["tickets"].insert_one.assert_called_once()

    def test_save_ticket_defaults_status_to_open(self):
        client = self._client()
        client._db["counters"].find_one_and_update.return_value = {"seq": 1}
        client.save_ticket({"user_name": "A"})
        doc = client._db["tickets"].insert_one.call_args[0][0]
        assert doc["status"] == "open"

    def test_save_ticket_retries_on_duplicate_id(self):
        from pymongo.errors import DuplicateKeyError
        client = self._client()
        client._db["counters"].find_one_and_update.side_effect = [
            {"seq": 1}, {"seq": 2},
        ]
        client._db["tickets"].insert_one.side_effect = [DuplicateKeyError("dup"), None]
        assert client.save_ticket({"user_name": "A"}).endswith("-0002")

    def test_knowledge_docs_strip_embeddings(self):
        client = self._client()
        client.save_knowledge_docs([
            {"id": "1", "instruction": "q", "embedding": [0.1, 0.2]},
        ])
        inserted = client._db["knowledge_base"].insert_many.call_args[0][0]
        assert "embedding" not in inserted[0]
        assert inserted[0]["instruction"] == "q"

    def test_empty_knowledge_docs_skips_insert(self):
        client = self._client()
        client.save_knowledge_docs([])
        client._db["knowledge_base"].insert_many.assert_not_called()

    def test_status_update_reports_success_on_no_op(self):
        client = self._client()
        result = MagicMock()
        result.matched_count = 1
        client._db["tickets"].update_one.return_value = result
        assert client.update_ticket_status("TKT-1", "resolved") is True

    def test_status_update_reports_missing_ticket(self):
        client = self._client()
        result = MagicMock()
        result.matched_count = 0
        client._db["tickets"].update_one.return_value = result
        assert client.update_ticket_status("TKT-NOPE", "resolved") is False


# ── VECTOR STORE ──────────────────────────────────────────────────────────────

DIM = 16


def _store(n_docs=3):
    import numpy as np
    from src.vector_store import FAISSVectorStore

    store = FAISSVectorStore(embedding_dimension=DIM)
    store.create_index()
    if n_docs:
        rng = np.random.default_rng(0)
        store.add_documents([
            {"id": str(i), "instruction": f"q{i}", "category": "Billing",
             "embedding": rng.random(DIM).astype("float32")}
            for i in range(n_docs)
        ])
    return store


class TestVectorStore:
    def test_documents_are_indexed(self):
        assert _store(3).get_stats()["total_documents"] == 3

    def test_search_returns_scored_documents(self):
        store = _store(3)
        results = store.search(store.documents[1]["embedding"], top_k=2)
        assert results and results[0][0]["id"] == "1"

    def test_identical_vector_scores_near_one(self):
        store = _store(3)
        _, score = store.search(store.documents[0]["embedding"], top_k=1)[0]
        assert score == pytest.approx(1.0, abs=1e-4)

    def test_zero_query_embedding_returns_nothing(self):
        import numpy as np
        # A zero vector is what GeminiEmbeddings yields on API failure
        assert _store(3).search(np.zeros(DIM, dtype="float32"), top_k=3) == []

    def test_empty_store_returns_nothing(self):
        import numpy as np
        assert _store(0).search(np.ones(DIM, dtype="float32"), top_k=3) == []

    def test_threshold_filters_weak_matches(self):
        store = _store(3)
        assert store.search(store.documents[0]["embedding"], top_k=3, threshold=1.01) == []

    def test_second_add_appends_instead_of_overwriting(self):
        import numpy as np
        store = _store(2)
        store.add_documents([
            {"id": "extra", "embedding": np.ones(DIM, dtype="float32")}
        ])
        assert store.get_stats()["total_documents"] == 3
        assert len(store.id_to_doc) == 3
        assert store.id_to_doc[2]["id"] == "extra"

    def test_missing_embedding_raises(self):
        store = _store(0)
        with pytest.raises(ValueError, match="missing 'embedding'"):
            store.add_documents([{"id": "1"}])

    def test_save_and_load_round_trip(self, tmp_path):
        store = _store(3)
        store.save(str(tmp_path))

        from src.vector_store import FAISSVectorStore
        reloaded = FAISSVectorStore(embedding_dimension=DIM)
        reloaded.load(str(tmp_path))

        assert reloaded.get_stats()["total_documents"] == 3
        assert reloaded.id_to_doc[0]["id"] == "0"

    def test_load_missing_index_raises(self, tmp_path):
        from src.vector_store import FAISSVectorStore
        with pytest.raises(FileNotFoundError):
            FAISSVectorStore(embedding_dimension=DIM).load(str(tmp_path))

    def test_clear_empties_the_store(self):
        store = _store(3)
        store.clear()
        assert store.get_stats()["total_documents"] == 0
        assert store.documents == []


# ── RAG ENGINE ────────────────────────────────────────────────────────────────

class TestRAGEngine:
    def _engine(self, results):
        from src.rag_engine import RAGEngine
        embedder, vector_store = MagicMock(), MagicMock()
        vector_store.search.return_value = results
        engine = RAGEngine(embedder=embedder, vector_store=vector_store)
        engine.is_initialized = True
        return engine

    def test_retrieve_before_init_raises(self):
        from src.rag_engine import RAGEngine
        engine = RAGEngine(embedder=MagicMock(), vector_store=MagicMock())
        with pytest.raises(RuntimeError, match="not initialized"):
            engine.retrieve("q")

    def test_context_reports_when_nothing_matches(self):
        assert self._engine([]).get_context("q") == "No relevant context found."

    def test_context_includes_retrieved_pairs(self):
        doc = {"instruction": "How do I pay?", "response": "Use the billing page",
               "category": "Billing"}
        context = self._engine([(doc, 0.9)]).get_context("q")
        assert "How do I pay?" in context and "Use the billing page" in context

    def test_similar_tickets_expose_rounded_scores(self):
        doc = {"id": "3", "instruction": "i", "response": "r", "category": "Billing"}
        tickets = self._engine([(doc, 0.123456)]).get_similar_tickets("q")
        assert tickets[0]["similarity_score"] == 0.1235

    def test_analyze_query_reports_no_results(self):
        assert self._engine([]).analyze_query("q")["has_results"] is False

    def test_analyze_query_suggests_dominant_category(self):
        docs = [({"category": "Billing"}, 0.9), ({"category": "Billing"}, 0.8),
                ({"category": "Returns & Refunds"}, 0.7)]
        analysis = self._engine(docs).analyze_query("q")
        assert analysis["suggested_category"] == "Billing"
        assert analysis["num_results"] == 3
        assert analysis["max_similarity"] == pytest.approx(0.9)


# ── EMAIL SERVICE ─────────────────────────────────────────────────────────────

class TestEmailService:
    def test_not_configured_without_credentials(self):
        from src.email_service import EmailService
        assert EmailService(gmail_address="", app_password="")._is_configured() is False

    def test_configured_with_credentials(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        assert service._is_configured() is True

    def test_customer_email_skipped_when_unconfigured(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="", app_password="")
        sent = service.send_customer_confirmation(
            to_email="c@example.com", user_name="C", ticket_id="TKT-1",
            category="Billing", priority="high", ai_response="hi", sla_hours=8,
        )
        assert sent is False

    def test_customer_email_body_carries_ticket_details(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(service, "_send", return_value=True) as send:
            service.send_customer_confirmation(
                to_email="c@example.com", user_name="Chris", ticket_id="TKT-42",
                category="Billing", priority="urgent", ai_response="Try X", sla_hours=2,
            )
        msg = send.call_args[0][0]
        body = msg.get_payload(0).get_payload(decode=True).decode()
        assert "TKT-42" in msg["Subject"]
        assert msg["To"] == "c@example.com"
        for expected in ("Chris", "Billing", "URGENT", "Within 2 hours", "Try X"):
            assert expected in body

    def test_developer_alert_lists_self_help_attempts(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(Config, "DEVELOPER_EMAIL", "dev@example.com"), \
             patch.object(service, "_send", return_value=True) as send:
            service.send_developer_alert(
                ticket_id="TKT-42", user_name="Chris", user_email="c@example.com",
                issue_description="It broke", category="Technical Support",
                priority="high", sentiment="negative", ai_response="Try X",
                attempt_history=["restarted the app", "cleared the cache"],
            )
        body = send.call_args[0][0].get_payload(0).get_payload(decode=True).decode()
        assert "restarted the app" in body and "cleared the cache" in body

    def test_developer_alert_skipped_without_developer_email(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(Config, "DEVELOPER_EMAIL", ""):
            sent = service.send_developer_alert(
                ticket_id="TKT-1", user_name="C", user_email="c@example.com",
                issue_description="x", category="Billing", priority="low",
                sentiment="neutral", ai_response="y",
            )
        assert sent is False

    def test_screenshot_is_attached(self, tmp_path):
        from src.email_service import EmailService
        shot = tmp_path / "screen.png"
        shot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)

        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(Config, "DEVELOPER_EMAIL", "dev@example.com"), \
             patch.object(service, "_send", return_value=True) as send:
            service.send_developer_alert(
                ticket_id="TKT-1", user_name="C", user_email="c@example.com",
                issue_description="x", category="Billing", priority="low",
                sentiment="neutral", ai_response="y", screenshot_path=str(shot),
            )
        assert len(send.call_args[0][0].get_payload()) == 2


# ── CONFIG ────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_validate_raises_when_keys_missing(self):
        with patch.object(Config, "GOOGLE_API_KEY", ""), \
             patch.object(Config, "GROQ_API_KEY", ""):
            with pytest.raises(ValueError) as exc:
                Config.validate()
        assert "GOOGLE_API_KEY" in str(exc.value)
        assert "GROQ_API_KEY" in str(exc.value)

    def test_validate_passes_with_keys(self):
        with patch.object(Config, "GOOGLE_API_KEY", "x"), \
             patch.object(Config, "GROQ_API_KEY", "y"):
            assert Config.validate() is True

    def test_every_priority_has_an_sla(self):
        assert set(Config.PRIORITY_LEVELS) == set(Config.PRIORITY_SLA)

    def test_sla_shortens_as_priority_rises(self):
        ordered = sorted(Config.PRIORITY_LEVELS, key=Config.PRIORITY_LEVELS.get)
        slas = [Config.PRIORITY_SLA[p] for p in ordered]
        assert slas == sorted(slas)


# ── TRANSLATOR ────────────────────────────────────────────────────────────────

class TestTranslator:
    def test_short_text_defaults_to_english(self):
        from src.translator import detect_language
        assert detect_language("hi") == "en"

    def test_empty_text_defaults_to_english(self):
        from src.translator import detect_language
        assert detect_language("") == "en"

    def test_detects_english_sentence(self):
        from src.translator import detect_language
        assert detect_language("I cannot log into my account today") == "en"

    def test_english_target_is_a_passthrough(self):
        from src.translator import translate_from_english
        assert translate_from_english("hello", "en") == "hello"

    def test_english_source_is_a_passthrough(self):
        from src.translator import translate_to_english
        assert translate_to_english("hello", "en") == "hello"

    def test_translation_failure_returns_original(self):
        import src.translator as translator
        with patch.object(translator, "GoogleTranslator", side_effect=RuntimeError("net down")):
            assert translator.translate_from_english("hello", "fr") == "hello"

    def test_known_language_name(self):
        from src.translator import get_language_name
        assert get_language_name("hi") == "Hindi"

    def test_unknown_language_name_falls_back_to_code(self):
        from src.translator import get_language_name
        assert get_language_name("xx") == "XX"
