import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()


class GroqLLMClient:
    """LLM Client wrapping Groq API with llama-3.1-8b-instant model."""

    MODEL_NAME = "llama-3.1-8b-instant"
    PARAMETER_SIZE = "8B"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.client = None
        if self.api_key:
            try:
                from groq import Groq
                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                print(f"[GroqLLMClient] Failed to initialize Groq client: {e}")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate text using llama-3.1-8b-instant on Groq."""
        if not self.client:
            return f"[Fallback Narrative] Groq client not active. Processed system prompt: {system_prompt[:50]}..."

        try:
            response = self.client.chat.completions.create(
                model=self.MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1000,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"[GroqLLMClient Error] {e}")
            return f"[Fallback Narrative due to error: {e}]"
