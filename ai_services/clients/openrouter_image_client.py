import base64
import os
import re

import requests
from dotenv import load_dotenv


load_dotenv()


class OpenRouterImageGenerationError(RuntimeError):
    """OpenRouter image generation failed or returned unusable data."""


class OpenRouterImageClient:
    """Generate one buffered image through OpenRouter's Unified Image API."""

    ENDPOINT = "https://openrouter.ai/api/v1/images"
    DEFAULT_SIZE = "1024x1024"

    def __init__(self, client=None):
        self.api_key = (
            os.getenv("OPENROUTER_API_KEY", "")
            or ""
        ).strip()
        self.model = (
            os.getenv("OPENROUTER_IMAGE_MODEL", "")
            or ""
        ).strip()
        if not self.api_key:
            raise OpenRouterImageGenerationError(
                "OPENROUTER_API_KEY is missing from the environment."
            )
        if not self.model:
            raise OpenRouterImageGenerationError(
                "OPENROUTER_IMAGE_MODEL is missing from the environment."
            )

        self.client = client or requests

    def _safe_error_message(self, exc):
        message = str(exc) or exc.__class__.__name__
        if self.api_key:
            message = message.replace(self.api_key, "[REDACTED]")
        message = re.sub(
            r"(?i)\bbearer\s+[A-Za-z0-9._-]+",
            "Bearer [REDACTED]",
            message,
        )
        message = re.sub(
            r"\bsk-or-v1-[A-Za-z0-9._-]+",
            "[REDACTED]",
            message,
        )
        return message[:2000]

    def generate_image(self, prompt, size=DEFAULT_SIZE):
        if not prompt or not str(prompt).strip():
            raise ValueError("Image prompt cannot be empty.")
        if size != self.DEFAULT_SIZE:
            raise ValueError("OpenRouter poster size must be 1024x1024.")

        try:
            response = self.client.post(
                self.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "prompt": str(prompt).strip(),
                    "n": 1,
                },
                timeout=120,
            )
        except Exception as exc:
            safe_message = self._safe_error_message(exc)
            raise OpenRouterImageGenerationError(
                f"OpenRouter image connection failed: {safe_message}"
            ) from None

        if not response.ok:
            try:
                details = response.json()
            except ValueError:
                details = response.text
            safe_details = self._safe_error_message(details)
            raise OpenRouterImageGenerationError(
                "OpenRouter image generation failed. "
                f"HTTP {response.status_code}: {safe_details}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenRouterImageGenerationError(
                "OpenRouter image generation returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise OpenRouterImageGenerationError(
                "OpenRouter image generation returned invalid JSON data."
            )

        data = payload.get("data")
        if not isinstance(data, list) or len(data) != 1:
            raise OpenRouterImageGenerationError(
                "OpenRouter did not return exactly one image in data."
            )

        image = data[0]
        if not isinstance(image, dict) or "b64_json" not in image:
            raise OpenRouterImageGenerationError(
                "OpenRouter image response did not contain b64_json."
            )

        image_base64 = image.get("b64_json")
        if not isinstance(image_base64, str):
            raise OpenRouterImageGenerationError(
                "OpenRouter image response contained invalid b64_json data."
            )

        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except Exception as exc:
            raise OpenRouterImageGenerationError(
                "OpenRouter image response contained invalid base64 data."
            ) from exc

        if not image_bytes:
            raise OpenRouterImageGenerationError(
                "OpenRouter image response decoded to an empty image."
            )
        return image_bytes
