"""
Response Generator Module
Generates customer support responses using Groq LLM with RAG context
"""

import json
from typing import List, Dict, Optional
from .config import Config, SYSTEM_PROMPTS
from .llm_client import GroqClient
from .rag_engine import RAGEngine
from .translator import detect_language, translate_to_english, translate_from_english


class ResponseGenerator:
    """Generates customer support responses using Groq LLM"""

    def __init__(self, api_key: Optional[str] = None, rag_engine: Optional[RAGEngine] = None):
        self.llm = GroqClient(api_key=api_key or Config.GROQ_API_KEY)
        self.rag_engine = rag_engine

    def set_rag_engine(self, rag_engine: RAGEngine):
        self.rag_engine = rag_engine

    def categorize_ticket(self, query: str) -> Dict:
        """
        Categorize a ticket: returns category, priority, sentiment, summary.
        Always processes in English.
        """
        prompt = SYSTEM_PROMPTS["categorization"].format(
            categories=", ".join(Config.TICKET_CATEGORIES)
        ) + f"\n\nCustomer Query: {query}"

        try:
            response_text = self.llm.generate(prompt, temperature=0.1)

            # Strip markdown code fences if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            return json.loads(response_text)

        except (json.JSONDecodeError, Exception):
            return {
                "category": "General Inquiry",
                "priority": "medium",
                "sentiment": "neutral",
                "summary": query[:100],
            }

    def generate_self_help(self, query: str) -> str:
        """
        Generate 2-3 self-help steps for the user to try before creating a ticket.
        Uses RAG context if available.
        """
        context = "No relevant context found."
        if self.rag_engine and self.rag_engine.is_initialized:
            context = self.rag_engine.get_context(query, top_k=3)

        prompt = SYSTEM_PROMPTS["self_help"].format(query=query, context=context)
        try:
            return self.llm.generate(prompt, temperature=0.5)
        except Exception as e:
            return f"Please check our FAQ or contact support directly. (Error: {e})"

    def generate_response(
        self,
        query: str,
        context: Optional[str] = None,
        use_rag: bool = True,
    ) -> str:
        """
        Generate a full support response using RAG context.
        """
        if use_rag and self.rag_engine and self.rag_engine.is_initialized and context is None:
            context = self.rag_engine.get_context(query)

        context = context or "No specific context available."

        prompt = SYSTEM_PROMPTS["response_generation"].format(
            query=query, context=context
        )
        try:
            return self.llm.generate(prompt, temperature=Config.TEMPERATURE)
        except Exception as e:
            return (
                "I apologize, but I'm having trouble generating a response. "
                f"Please contact our support team directly. (Error: {e})"
            )

    def generate_multiple_responses(
        self, query: str, num_candidates: int = None
    ) -> List[Dict]:
        """Generate multiple response candidates at varying temperatures."""
        num_candidates = num_candidates or Config.NUM_RESPONSE_CANDIDATES
        context = None
        if self.rag_engine and self.rag_engine.is_initialized:
            context = self.rag_engine.get_context(query)

        temperatures = [0.3, 0.7, 1.0]
        responses = []

        for i in range(num_candidates):
            temp = temperatures[i % len(temperatures)]
            prompt = SYSTEM_PROMPTS["response_generation"].format(
                query=query,
                context=context or "No specific context available.",
            )
            try:
                text = self.llm.generate(prompt, temperature=temp)
                responses.append({
                    "id": i + 1,
                    "text": text,
                    "temperature": temp,
                    "style": "conservative" if temp < 0.5 else ("balanced" if temp < 0.8 else "creative"),
                })
            except Exception as e:
                responses.append({
                    "id": i + 1,
                    "text": f"Error generating response: {e}",
                    "temperature": temp,
                    "style": "error",
                })

        return responses

    def improve_response(self, original_response: str, feedback: str) -> str:
        """Improve a response based on user feedback."""
        prompt = SYSTEM_PROMPTS["response_improvement"].format(
            original_response=original_response, feedback=feedback
        )
        try:
            return self.llm.generate(prompt, temperature=0.5)
        except Exception:
            return original_response

    def generate_with_analysis(self, query: str, user_lang: str = "en") -> Dict:
        """
        Full pipeline: detect language → translate → categorize → RAG response
        → translate back → collect similar tickets.

        Args:
            query: Raw user query (any language)
            user_lang: Detected language of the query

        Returns:
            Dict with: query, english_query, response, categorization,
                       similar_tickets, language
        """
        # Translate to English for processing
        english_query = translate_to_english(query, src_lang=user_lang) if user_lang != "en" else query

        # Categorize (uses English query)
        categorization = self.categorize_ticket(english_query)

        # Get similar tickets
        similar_tickets = []
        if self.rag_engine and self.rag_engine.is_initialized:
            similar_tickets = self.rag_engine.get_similar_tickets(english_query, top_k=3)

        # Generate response (English)
        response_en = self.generate_response(english_query)

        # Translate response back to user's language
        response = translate_from_english(response_en, user_lang) if user_lang != "en" else response_en

        return {
            "query": query,
            "english_query": english_query,
            "response": response,
            "response_en": response_en,
            "categorization": categorization,
            "similar_tickets": similar_tickets,
            "language": user_lang,
        }


class FeedbackLoop:
    """Manages the response improvement feedback loop"""

    def __init__(self, response_generator: ResponseGenerator, db_client=None):
        self.generator = response_generator
        self.db = db_client
        self._memory_history = []  # fallback if no DB

    def submit_feedback(
        self,
        query: str,
        original_response: str,
        feedback: str,
        rating: int = None,
    ) -> Dict:
        improved_response = self.generator.improve_response(original_response, feedback)

        record = {
            "query": query,
            "original_response": original_response,
            "feedback": feedback,
            "rating": rating,
            "improved_response": improved_response,
        }

        if self.db:
            try:
                self.db.save_feedback(record)
            except Exception:
                self._memory_history.append(record)
        else:
            self._memory_history.append(record)

        return {
            "improved_response": improved_response,
            "feedback_id": len(self._memory_history),
        }

    def get_feedback_history(self) -> List[Dict]:
        if self.db:
            try:
                return self.db.get_all_feedback()
            except Exception:
                pass
        return self._memory_history
