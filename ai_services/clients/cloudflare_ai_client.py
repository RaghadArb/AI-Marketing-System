import os

import requests
from dotenv import load_dotenv


load_dotenv()


class CloudflareAIClient:
    """
    Cloudflare Workers AI client for TEXT generation only.

    Model:
        @cf/meta/llama-3.3-70b-instruct-fp8-fast

    This client intentionally contains:
    - no Ollama fallback
    - no image-generation model
    - no localhost dependency
    """

    DEFAULT_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

    def __init__(self):
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.model = os.getenv(
            "CLOUDFLARE_TEXT_MODEL",
            self.DEFAULT_MODEL,
        )

        if not self.account_id:
            raise RuntimeError(
                "CLOUDFLARE_ACCOUNT_ID is missing from .env"
            )

        if not self.api_token:
            raise RuntimeError(
                "CLOUDFLARE_API_TOKEN is missing from .env"
            )

        self.url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/{self.model}"
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

        try:
            response = requests.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Cloudflare text generation connection failed: {exc}"
            ) from exc

        if not response.ok:
            try:
                details = response.json()
            except ValueError:
                details = response.text

            raise RuntimeError(
                "Cloudflare text generation failed. "
                f"HTTP {response.status_code}: {details}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Cloudflare text generation returned invalid JSON."
            ) from exc

        if not payload.get("success", True):
            raise RuntimeError(
                "Cloudflare text generation failed: "
                f"{payload.get('errors', payload)}"
            )

        result = payload.get("result", {})

        if isinstance(result, str):
            text = result.strip()

        elif isinstance(result, dict):
            text = (
                result.get("response")
                or result.get("text")
                or result.get("output")
                or ""
            )

            if not isinstance(text, str):
                text = str(text)

            text = text.strip()

        else:
            text = ""

        if not text:
            raise RuntimeError(
                "Cloudflare text generation returned an empty response."
            )

        return text
