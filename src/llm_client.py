"""
LLM Client Module
Wraps Groq API for response generation
"""

from groq import Groq
from typing import Optional
from .config import Config


class GroqClient:
    """Groq LLM client for generating customer support responses"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.GROQ_API_KEY
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY is required. Get a free key at https://console.groq.com"
            )
        self.client = Groq(api_key=self.api_key)
        self.model = Config.LLM_MODEL

    def generate(self, prompt: str, temperature: float = None, max_tokens: int = None) -> str:
        """
        Generate a response for the given prompt.

        Args:
            prompt: The full prompt string
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens in response

        Returns:
            Generated text string
        """
        temperature = temperature if temperature is not None else Config.TEMPERATURE
        max_tokens = max_tokens or Config.MAX_RESPONSE_TOKENS

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"Groq API error: {e}") from e

    def generate_with_system(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """
        Generate with a separate system prompt.

        Args:
            system_prompt: System-level instruction
            user_message: User turn content
            temperature: Sampling temperature
            max_tokens: Max response tokens

        Returns:
            Generated text string
        """
        temperature = temperature if temperature is not None else Config.TEMPERATURE
        max_tokens = max_tokens or Config.MAX_RESPONSE_TOKENS

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"Groq API error: {e}") from e
