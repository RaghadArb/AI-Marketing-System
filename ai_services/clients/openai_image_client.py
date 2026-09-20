import base64
import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


class OpenAIImageGenerationError(RuntimeError):
    """OpenAI image generation failed or returned unusable image data."""


class OpenAIImageClient:
    """Small OpenAI Images API client that always requests one PNG image."""

    DEFAULT_MODEL = "gpt-image-2"
    DEFAULT_SIZE = "1024x1024"
    DEFAULT_QUALITY = "medium"
    DEFAULT_OUTPUT_FORMAT = "png"

    def __init__(self, client=None):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv(
            "OPENAI_IMAGE_MODEL",
            self.DEFAULT_MODEL,
        )

        if client is None and not self.api_key:
            raise OpenAIImageGenerationError(
                "OPENAI_API_KEY is missing from the environment."
            )

        self.client = client or OpenAI(api_key=self.api_key)

    def generate_image(
        self,
        prompt,
        size=DEFAULT_SIZE,
        quality=DEFAULT_QUALITY,
        output_format=DEFAULT_OUTPUT_FORMAT,
    ):
        if not prompt or not str(prompt).strip():
            raise ValueError("Image prompt cannot be empty.")

        try:
            response = self.client.images.generate(
                model=self.model,
                prompt=str(prompt).strip(),
                size=size,
                quality=quality,
                output_format=output_format,
                n=1,
            )
        except OpenAIImageGenerationError:
            raise
        except Exception as exc:
            raise OpenAIImageGenerationError(
                f"OpenAI image generation failed: {exc}"
            ) from exc

        data = getattr(response, "data", None)
        if not data or len(data) != 1:
            raise OpenAIImageGenerationError(
                "OpenAI image generation did not return exactly one image."
            )

        item = data[0]
        image_base64 = (
            item.get("b64_json")
            if isinstance(item, dict)
            else getattr(item, "b64_json", None)
        )
        if not image_base64:
            raise OpenAIImageGenerationError(
                "OpenAI image response did not contain base64 image data."
            )

        try:
            image_bytes = base64.b64decode(
                image_base64,
                validate=True,
            )
        except Exception as exc:
            raise OpenAIImageGenerationError(
                "OpenAI image response contained invalid base64 data."
            ) from exc

        if not image_bytes:
            raise OpenAIImageGenerationError(
                "OpenAI image response decoded to an empty image."
            )

        return image_bytes
