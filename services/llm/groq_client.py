"""
MedIntel Groq API Client Wrapper
Provides safe, thread-safe access to Groq LLM services with timeout handling,
rate-limit resilience (429 retry), and fail-safe exception management.
"""

import os
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Load .env variables if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class GroqClientWrapper:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        self.timeout = float(os.getenv("GROQ_TIMEOUT_SECONDS", "5.0"))
        self.max_tokens = int(os.getenv("GROQ_MAX_OUTPUT_TOKENS", "512"))
        self.enabled = os.getenv("LLM_ENABLED", "true").lower() in ("true", "1", "yes")
        self._client = None

    def is_configured(self) -> bool:
        """Returns True if Groq API key is present and LLM feature is enabled."""
        return bool(self.enabled and self.api_key)

    def _get_client(self):
        if self._client is None and self.is_configured():
            try:
                import groq
                self._client = groq.Groq(api_key=self.api_key, timeout=self.timeout)
            except Exception as e:
                logger.warning(f"[GROQ CLIENT] Failed to initialize Groq client: {e}")
                self._client = None
        return self._client

    def generate_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        retries: int = 2
    ) -> Optional[str]:
        """
        Executes chat completion request against Groq API with retries for 429 Rate Limits.
        Returns raw string content or None if API call fails/times out.
        """
        client = self._get_client()
        if not client:
            logger.info("[GROQ CLIENT] Groq client not configured or disabled.")
            return None

        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                    max_tokens=self.max_tokens,
                    response_format={"type": "json_object"}
                )
                if response and response.choices and response.choices[0].message:
                    return response.choices[0].message.content
                return None
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate limit" in err_str.lower():
                    logger.warning(f"[GROQ CLIENT] Rate limit (429) hit on attempt {attempt + 1}. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    logger.error(f"[GROQ CLIENT] Exception during Groq API invocation: {e}")
                    return None
        return None
