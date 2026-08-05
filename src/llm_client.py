import os
import time
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class GroqLLMClient:
    """LLM Client wrapping Groq API with llama-3.1-8b-instant model."""

    MODEL_NAME = "llama-3.1-8b-instant"
    PARAMETER_SIZE = "8B"
    MAX_RETRIES = 4
    BASE_DELAY = 1.0  # seconds

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
        """Generate text using llama-3.1-8b-instant on Groq, with retry on rate limit."""
        if not self.client:
            return f"[Fallback Narrative] Groq client not active. Processed system prompt: {system_prompt[:50]}..."

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=300,  # reduced to stay under TPM limit
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate_limit" in err_str:
                    delay = self.BASE_DELAY * (2 ** attempt)
                    print(f"[GroqLLMClient] Rate limited, retrying in {delay:.1f}s (attempt {attempt + 1}/{self.MAX_RETRIES})...")
                    time.sleep(delay)
                else:
                    print(f"[GroqLLMClient Error] {e}")
                    return f"[Fallback Narrative due to error: {e}]"

        return "[Fallback Narrative] Max retries exceeded due to rate limit."
