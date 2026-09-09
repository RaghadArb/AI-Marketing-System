import os

import requests
from dotenv import load_dotenv


load_dotenv()


class FallbackAIClient:
    """
    Personal OpenAI-compatible text client.

    Used only as a quota/rate-limit fallback for Cloudflare
    text generation. Configuration comes from .env:

        FALLBACK_AI_BASE_URL
        FALLBACK_AI_API_KEY
        FALLBACK_AI_MODEL
    """

    def __init__(self):
        self.base_url = (
            os.getenv("FALLBACK_AI_BASE_URL", "")
            or ""
        ).strip().rstrip("/")

        self.api_key = (
            os.getenv("FALLBACK_AI_API_KEY", "")
            or ""
        ).strip()

        self.model = (
            os.getenv("FALLBACK_AI_MODEL", "")
            or ""
        ).strip()

    def is_configured(self):
        return bool(
            self.base_url
            and self.api_key
            and self.model
        )

    def generate(
        self,
        prompt,
        system_prompt=None,
        temperature=0.7,
        max_tokens=1600,
    ):
        if not prompt or not str(prompt).strip():
            raise ValueError("Prompt cannot be empty.")

        if not self.is_configured():
            raise RuntimeError(
                "Fallback AI is not configured. Set "
                "FALLBACK_AI_BASE_URL, FALLBACK_AI_API_KEY, "
                "and FALLBACK_AI_MODEL in .env."
            )

        messages = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": str(prompt).strip(),
            }
        )

        if self.base_url.endswith("/chat/completions"):
            url = self.base_url
        else:
            url = f"{self.base_url}/chat/completions"

        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Fallback text generation connection failed: {exc}"
            ) from exc

        if not response.ok:
            try:
                details = response.json()
            except ValueError:
                details = response.text

            raise RuntimeError(
                "Fallback text generation failed. "
                f"HTTP {response.status_code}: {details}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Fallback text generation returned invalid JSON."
            ) from exc

        text = ""
        choices = payload.get("choices") or []

        if choices:
            first = choices[0] or {}
            message = first.get("message") or {}
            text = (
                message.get("content")
                or first.get("text")
                or ""
            )

        if not isinstance(text, str):
            text = str(text)

        text = text.strip()

        if not text:
            raise RuntimeError(
                "Fallback text generation returned an empty response."
            )

        return text
