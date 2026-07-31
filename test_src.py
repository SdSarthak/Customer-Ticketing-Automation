"""
Unit tests for the src/ modules.

These cover the pure logic — data loading, categorization normalization, the
feedback loop, ticket ID allocation and email formatting. No network calls:
Groq, Gemini and MongoDB are all mocked.
"""

import datetime
import json
import os
from types import SimpleNamespace
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

    def test_zero_embedding_documents_are_not_indexed(self):
        import numpy as np
        store = _store(0)
        store.add_documents([
            {"id": "blank", "embedding": np.zeros(DIM, dtype="float32")},
            {"id": "real", "embedding": np.ones(DIM, dtype="float32")},
        ])
        # A zero vector matches nothing, so counting it would hide a broken build
        assert store.get_stats()["total_documents"] == 1
        assert [d["id"] for d in store.documents] == ["real"]

    def test_ids_stay_contiguous_when_documents_are_skipped(self):
        import numpy as np
        store = _store(0)
        store.add_documents([
            {"id": "blank", "embedding": np.zeros(DIM, dtype="float32")},
            {"id": "real", "embedding": np.ones(DIM, dtype="float32")},
        ])
        # The kept document must own id 0 — a gap would desync id_to_doc
        assert store.id_to_doc[0]["id"] == "real"
        results = store.search(np.ones(DIM, dtype="float32"), top_k=1)
        assert results[0][0]["id"] == "real"

    def test_all_zero_batch_indexes_nothing(self):
        import numpy as np
        store = _store(0)
        store.add_documents([
            {"id": str(i), "embedding": np.zeros(DIM, dtype="float32")}
            for i in range(3)
        ])
        assert store.get_stats()["total_documents"] == 0


# ── EMBEDDINGS ────────────────────────────────────────────────────────────────

def _embedder(side_effect):
    """Build a GeminiEmbeddings whose underlying API call is mocked."""
    from src.embeddings import GeminiEmbeddings

    with patch("src.embeddings.genai.Client"):
        embedder = GeminiEmbeddings(api_key="test-key")
    embedder.embedding_dimension = 4
    embedder.client.models.embed_content.side_effect = side_effect
    return embedder


def _ok(*_args, **_kwargs):
    """A successful embed_content response carrying a unit vector."""
    result = MagicMock()
    result.embeddings = [MagicMock(values=[1.0, 0.0, 0.0, 0.0])]
    return result


def _boom(*_args, **_kwargs):
    raise RuntimeError("401 invalid api key")


class TestEmbeddings:
    def test_requires_an_api_key(self):
        from src.embeddings import GeminiEmbeddings
        with patch.object(Config, "GOOGLE_API_KEY", ""):
            with pytest.raises(ValueError, match="API key"):
                GeminiEmbeddings()

    def test_query_embedding_degrades_to_zero_vector(self):
        import numpy as np
        embedder = _embedder(_boom)
        # A failed lookup must not 500 the request — the store skips zero vectors
        assert not np.any(embedder.create_query_embedding("hello"))

    def test_document_embedding_degrades_to_zero_vector(self):
        import numpy as np
        assert not np.any(_embedder(_boom).create_embedding("hello"))

    def test_blank_text_needs_no_api_call(self):
        embedder = _embedder(_ok)
        embedder.create_embedding("   ")
        embedder.client.models.embed_content.assert_not_called()

    def test_embed_documents_aborts_when_every_call_fails(self):
        from src.embeddings import EmbeddingError
        embedder = _embedder(_boom)
        docs = [{"combined_text": f"doc {i}"} for i in range(10)]
        with pytest.raises(EmbeddingError, match="consecutive embedding calls failed"):
            embedder.embed_documents(docs)

    def test_embed_documents_stops_before_burning_the_corpus(self):
        from src.embeddings import EmbeddingError
        embedder = _embedder(_boom)
        docs = [{"combined_text": f"doc {i}"} for i in range(50)]
        with pytest.raises(EmbeddingError):
            embedder.embed_documents(docs)
        assert embedder.client.models.embed_content.call_count == \
            embedder.FAIL_FAST_THRESHOLD

    def test_embed_documents_tolerates_one_transient_failure(self):
        import numpy as np
        embedder = _embedder([RuntimeError("boom"), _ok(), _ok(), _ok()])
        docs = [{"combined_text": f"doc {i}"} for i in range(4)]
        embedder.embed_documents(docs)
        # The one failure yields a zero vector; the rest embed normally
        assert not np.any(docs[0]["embedding"])
        assert all(np.any(d["embedding"]) for d in docs[1:])

    def test_success_resets_the_consecutive_failure_counter(self):
        embedder = _embedder([
            RuntimeError("boom"), RuntimeError("boom"), _ok(),
            RuntimeError("boom"), RuntimeError("boom"), _ok(),
        ])
        docs = [{"combined_text": f"doc {i}"} for i in range(6)]
        # Never 3 in a row, so the run completes despite 4 total failures
        embedder.embed_documents(docs)
        assert embedder._failed_total == 4


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

    def test_empty_index_is_not_reported_as_initialized(self):
        from src.rag_engine import RAGEngine
        embedder, vector_store = MagicMock(), MagicMock()
        embedder.embed_documents.return_value = [{"combined_text": "x"}]
        vector_store.get_stats.return_value = {"total_documents": 0}
        engine = RAGEngine(embedder=embedder, vector_store=vector_store)

        with pytest.raises(ValueError, match="usable embedding"):
            engine.initialize_from_documents([{"combined_text": "x"}])
        assert engine.is_initialized is False

    def test_successful_build_marks_engine_initialized(self):
        from src.rag_engine import RAGEngine
        embedder, vector_store = MagicMock(), MagicMock()
        embedder.embed_documents.return_value = [{"combined_text": "x"}]
        vector_store.get_stats.return_value = {"total_documents": 1}
        engine = RAGEngine(embedder=embedder, vector_store=vector_store)

        engine.initialize_from_documents([{"combined_text": "x"}])
        assert engine.is_initialized is True


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

    def test_customer_email_escapes_html_in_user_fields(self):
        """A customer name/response containing markup must not become live HTML."""
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(service, "_send", return_value=True) as send:
            service.send_customer_confirmation(
                to_email="c@example.com",
                user_name="<script>alert(1)</script>",
                ticket_id="TKT-42", category="Billing", priority="urgent",
                ai_response="</div><img src=x onerror=alert(2)>",
                sla_hours=2,
            )
        body = send.call_args[0][0].get_payload(0).get_payload(decode=True).decode()
        assert "<script>" not in body
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
        assert "<img" not in body
        assert "&lt;img src=x onerror=alert(2)&gt;" in body

    def test_developer_alert_escapes_issue_and_attempts(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(Config, "DEVELOPER_EMAIL", "dev@example.com"), \
             patch.object(service, "_send", return_value=True) as send:
            service.send_developer_alert(
                ticket_id="TKT-1", user_name="<b>C</b>", user_email="c@example.com",
                issue_description="<iframe src=evil></iframe>",
                category="Billing", priority="low", sentiment="neutral",
                ai_response="ok", attempt_history=["<script>x</script>"],
            )
        body = send.call_args[0][0].get_payload(0).get_payload(decode=True).decode()
        assert "<iframe" not in body
        assert "<script>x</script>" not in body
        assert "&lt;b&gt;C&lt;/b&gt;" in body

    def test_newlines_in_issue_still_render_as_breaks(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(Config, "DEVELOPER_EMAIL", "dev@example.com"), \
             patch.object(service, "_send", return_value=True) as send:
            service.send_developer_alert(
                ticket_id="TKT-1", user_name="C", user_email="c@example.com",
                issue_description="line one\nline two", category="Billing",
                priority="low", sentiment="neutral", ai_response="y",
            )
        body = send.call_args[0][0].get_payload(0).get_payload(decode=True).decode()
        assert "line one<br>line two" in body

    def test_subject_cannot_carry_injected_headers(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(service, "_send", return_value=True) as send:
            service.send_customer_confirmation(
                to_email="c@example.com", user_name="C",
                ticket_id="TKT-1\r\nBcc: attacker@evil.com",
                category="Billing", priority="low", ai_response="y", sla_hours=8,
            )
        msg = send.call_args[0][0]
        assert "\n" not in msg["Subject"] and "\r" not in msg["Subject"]
        assert msg["Bcc"] is None

    def test_invalid_recipient_is_rejected(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with pytest.raises(ValueError):
            service.send_customer_confirmation(
                to_email="not-an-email", user_name="C", ticket_id="TKT-1",
                category="Billing", priority="low", ai_response="y", sla_hours=8,
            )

    def test_oversized_screenshot_is_not_attached(self, tmp_path):
        from src.email_service import EmailService
        import src.email_service as email_module

        shot = tmp_path / "big.png"
        shot.write_bytes(b"0" * 2048)

        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(email_module, "MAX_ATTACHMENT_BYTES", 1024), \
             patch.object(Config, "DEVELOPER_EMAIL", "dev@example.com"), \
             patch.object(service, "_send", return_value=True) as send:
            service.send_developer_alert(
                ticket_id="TKT-1", user_name="C", user_email="c@example.com",
                issue_description="x", category="Billing", priority="low",
                sentiment="neutral", ai_response="y", screenshot_path=str(shot),
            )
        # body only — the oversized attachment was dropped, not sent
        assert len(send.call_args[0][0].get_payload()) == 1

    def test_missing_screenshot_path_does_not_raise(self):
        from src.email_service import EmailService
        service = EmailService(gmail_address="a@gmail.com", app_password="pw")
        with patch.object(Config, "DEVELOPER_EMAIL", "dev@example.com"), \
             patch.object(service, "_send", return_value=True) as send:
            sent = service.send_developer_alert(
                ticket_id="TKT-1", user_name="C", user_email="c@example.com",
                issue_description="x", category="Billing", priority="low",
                sentiment="neutral", ai_response="y",
                screenshot_path="does/not/exist.png",
            )
        assert sent is True
        assert len(send.call_args[0][0].get_payload()) == 1


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

    def test_short_latin_phrase_falls_back_to_english(self):
        # Too little signal to trust — langdetect calls this Italian
        from src.translator import detect_language
        assert detect_language("cannot log in") == "en"

    def test_detects_non_latin_script_despite_short_length(self):
        from src.translator import detect_language
        assert detect_language("मेरा ऑर्डर कहाँ है") == "hi"

    def test_detects_long_latin_sentence(self):
        from src.translator import detect_language
        assert detect_language("Je ne peux pas me connecter a mon compte aujourd hui") == "fr"

    def test_detection_is_deterministic(self):
        from src.translator import detect_language
        text = "मेरा ऑर्डर अभी तक नहीं आया है"
        assert len({detect_language(text) for _ in range(5)}) == 1

    def test_low_confidence_falls_back_to_english(self):
        import src.translator as translator
        guess = SimpleNamespace(lang="fr", prob=0.42)
        with patch.object(translator, "detect_langs", return_value=[guess]):
            assert translator.detect_language("a fairly long ambiguous sentence") == "en"

    def test_unsupported_language_falls_back_to_english(self):
        import src.translator as translator
        guess = SimpleNamespace(lang="cy", prob=0.99)
        with patch.object(translator, "detect_langs", return_value=[guess]):
            assert translator.detect_language("a fairly long ambiguous sentence") == "en"

    def test_supported_language_is_reported(self):
        import src.translator as translator
        guess = SimpleNamespace(lang="de", prob=0.99)
        with patch.object(translator, "detect_langs", return_value=[guess]):
            assert translator.detect_language("a fairly long ambiguous sentence") == "de"

    def test_empty_candidate_list_falls_back_to_english(self):
        import src.translator as translator
        with patch.object(translator, "detect_langs", return_value=[]):
            assert translator.detect_language("a fairly long ambiguous sentence") == "en"

    def test_detector_error_falls_back_to_english(self):
        import src.translator as translator
        with patch.object(translator, "detect_langs", side_effect=RuntimeError("boom")):
            assert translator.detect_language("a fairly long ambiguous sentence") == "en"

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

    # ── timeouts and long input ───────────────────────────────────────────────

    def test_hanging_translation_does_not_block_forever(self):
        """deep_translator has no request timeout; the wrapper must impose one."""
        import time
        import src.translator as translator

        def _hang(*_a, **_k):
            time.sleep(30)
            return "never"

        fake = MagicMock()
        fake.translate.side_effect = _hang

        started = time.monotonic()
        with patch.object(translator, "GoogleTranslator", return_value=fake), \
             patch.object(translator, "TRANSLATION_TIMEOUT", 0.2):
            out = translator.translate_from_english("hello there", "fr")
        elapsed = time.monotonic() - started

        assert out == "hello there"      # degrades to the original, not a hang
        assert elapsed < 5               # and returns promptly

    def test_long_text_is_chunked_under_the_api_limit(self):
        """>5000 chars used to raise NotValidLength and never get translated."""
        import src.translator as translator

        long_text = ("Sentence number one. " * 600).strip()  # ~12k chars
        assert len(long_text) > 5000

        seen = []

        def _translate(chunk):
            seen.append(chunk)
            return chunk.upper()

        fake = MagicMock()
        fake.translate.side_effect = _translate

        with patch.object(translator, "GoogleTranslator", return_value=fake):
            out = translator.translate_from_english(long_text, "fr")

        assert len(seen) > 1
        assert all(len(c) <= translator.MAX_CHARS_PER_REQUEST for c in seen)
        assert "".join(seen) == long_text          # nothing dropped or duplicated
        assert out == long_text.upper()

    def test_short_text_is_sent_as_a_single_call(self):
        import src.translator as translator
        fake = MagicMock()
        fake.translate.return_value = "bonjour"
        with patch.object(translator, "GoogleTranslator", return_value=fake):
            assert translator.translate_from_english("hello", "fr") == "bonjour"
        assert fake.translate.call_count == 1

    def test_split_is_lossless_and_prefers_boundaries(self):
        from src.translator import _split_for_translation

        text = "\n".join(f"Line {i} with some filler words." for i in range(500))
        chunks = _split_for_translation(text, limit=200)
        assert len(chunks) > 1
        assert all(len(c) <= 200 for c in chunks)
        assert "".join(chunks) == text

    def test_split_handles_text_with_no_boundaries(self):
        from src.translator import _split_for_translation
        text = "x" * 1000
        chunks = _split_for_translation(text, limit=300)
        assert "".join(chunks) == text
        assert all(len(c) <= 300 for c in chunks)

    def test_blank_text_never_hits_the_network(self):
        import src.translator as translator
        fake = MagicMock()
        with patch.object(translator, "GoogleTranslator", return_value=fake):
            assert translator.translate_from_english("   ", "fr") == "   "
            assert translator.translate_to_english("", "fr") == ""
        fake.translate.assert_not_called()

    def test_translator_error_inside_worker_returns_original(self):
        import src.translator as translator
        fake = MagicMock()
        fake.translate.side_effect = ValueError("bad payload")
        with patch.object(translator, "GoogleTranslator", return_value=fake):
            assert translator.translate_to_english("hola amigo", "es") == "hola amigo"

    def test_timeout_env_override_ignores_junk(self):
        from src.translator import _positive_float
        with patch.dict(os.environ, {"T_TEST": "not-a-number"}):
            assert _positive_float("T_TEST", 8.0) == 8.0
        with patch.dict(os.environ, {"T_TEST": "-3"}):
            assert _positive_float("T_TEST", 8.0) == 8.0
        with patch.dict(os.environ, {"T_TEST": "2.5"}):
            assert _positive_float("T_TEST", 8.0) == 2.5
