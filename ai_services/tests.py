import base64
import os
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from django.test import SimpleTestCase
from PIL import Image


class VectorStoreBackupSerializationTests(SimpleTestCase):
    def test_embedding_arrays_are_exported_as_json_lists(self):
        from ai_services.rag.vector_store import VectorStore

        store = VectorStore.__new__(VectorStore)
        store.collection = MagicMock()
        store.collection.get.side_effect = [
            {
                "ids": ["1_0"],
                "documents": ["Delivery takes two days."],
                "metadatas": [{"company_id": 1}],
            },
            {
                "ids": ["1_0"],
                "documents": ["Delivery takes two days."],
                "embeddings": np.array([[0.1, 0.2]], dtype=np.float32),
            },
        ]

        with patch("ai_services.rag.vector_store.os.makedirs"), patch(
            "ai_services.rag.vector_store._write_json_atomic"
        ) as write_json:
            store.export_backup_files()

        embedding_export = write_json.call_args_list[1].args[1]
        self.assertIsInstance(embedding_export[0]["embedding"], list)
        self.assertEqual(len(embedding_export[0]["embedding"]), 2)


def _png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class OpenRouterImageClientTests(SimpleTestCase):
    API_KEY = "sk-or-v1-test-secret"
    MODEL = "openai/example-image-model"

    def _client(self, http_client):
        from ai_services.clients.openrouter_image_client import (
            OpenRouterImageClient,
        )

        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": self.API_KEY,
                "OPENROUTER_IMAGE_MODEL": self.MODEL,
            },
        ):
            return OpenRouterImageClient(client=http_client)

    def _response(self, payload, ok=True, status=200):
        response = MagicMock()
        response.ok = ok
        response.status_code = status
        response.text = "mock response"
        response.json.return_value = payload
        return response

    def test_images_endpoint_decodes_b64_and_requests_one_image(self):
        png = _png_bytes()
        http_client = MagicMock()
        http_client.post.return_value = self._response(
            {
                "data": [
                    {
                        "b64_json": base64.b64encode(png).decode("ascii")
                    }
                ]
            }
        )
        client = self._client(http_client)

        result = client.generate_image("A product photograph")

        self.assertEqual(result, png)
        http_client.post.assert_called_once_with(
            "https://openrouter.ai/api/v1/images",
            headers={
                "Authorization": f"Bearer {self.API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.MODEL,
                "prompt": "A product photograph",
                "n": 1,
            },
            timeout=120,
        )

    def test_missing_data_is_rejected(self):
        from ai_services.clients.openrouter_image_client import (
            OpenRouterImageGenerationError,
        )

        http_client = MagicMock()
        http_client.post.return_value = self._response(
            {"created": 123}
        )
        client = self._client(http_client)

        with self.assertRaises(OpenRouterImageGenerationError):
            client.generate_image("A product photograph")

    def test_missing_b64_json_is_rejected(self):
        from ai_services.clients.openrouter_image_client import (
            OpenRouterImageGenerationError,
        )

        http_client = MagicMock()
        http_client.post.return_value = self._response(
            {"data": [{}]}
        )
        client = self._client(http_client)

        with self.assertRaises(OpenRouterImageGenerationError):
            client.generate_image("A product photograph")

    def test_malformed_base64_is_rejected(self):
        from ai_services.clients.openrouter_image_client import (
            OpenRouterImageGenerationError,
        )

        http_client = MagicMock()
        http_client.post.return_value = self._response(
            {"data": [{"b64_json": "not-valid-base64!"}]}
        )
        client = self._client(http_client)

        with self.assertRaises(OpenRouterImageGenerationError):
            client.generate_image("A product photograph")

    def test_empty_image_bytes_are_rejected(self):
        from ai_services.clients.openrouter_image_client import (
            OpenRouterImageGenerationError,
        )

        http_client = MagicMock()
        http_client.post.return_value = self._response(
            {"data": [{"b64_json": ""}]}
        )
        client = self._client(http_client)

        with self.assertRaises(OpenRouterImageGenerationError):
            client.generate_image("A product photograph")

    def test_invalid_json_is_rejected(self):
        from ai_services.clients.openrouter_image_client import (
            OpenRouterImageGenerationError,
        )

        http_client = MagicMock()
        response = self._response({})
        response.json.side_effect = ValueError("invalid JSON")
        http_client.post.return_value = response
        client = self._client(http_client)

        with self.assertRaises(OpenRouterImageGenerationError):
            client.generate_image("A product photograph")

    def test_http_failure_is_sanitized(self):
        from ai_services.clients.openrouter_image_client import (
            OpenRouterImageGenerationError,
        )

        http_client = MagicMock()
        http_client.post.return_value = self._response(
            {
                "error": (
                    f"Authorization: Bearer {self.API_KEY}"
                )
            },
            ok=False,
            status=401,
        )
        client = self._client(http_client)

        with self.assertRaises(OpenRouterImageGenerationError) as raised:
            client.generate_image("A product photograph")

        message = str(raised.exception)
        self.assertNotIn(self.API_KEY, message)
        self.assertNotIn("Bearer sk-", message)
        self.assertIn("[REDACTED]", message)


class OpenAIImageClientTests(SimpleTestCase):
    def _client(self, sdk_client):
        from ai_services.clients.openai_image_client import OpenAIImageClient

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_IMAGE_MODEL": "gpt-image-2",
            },
        ):
            return OpenAIImageClient(client=sdk_client)

    def test_decodes_base64_and_requests_exactly_one_image(self):
        png = _png_bytes()
        sdk_client = MagicMock()
        sdk_client.images.generate.return_value = SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(png).decode("ascii")
                )
            ]
        )

        client = self._client(sdk_client)
        result = client.generate_image("A product photograph")

        self.assertEqual(result, png)
        sdk_client.images.generate.assert_called_once_with(
            model="gpt-image-2",
            prompt="A product photograph",
            size="1024x1024",
            quality="medium",
            output_format="png",
            n=1,
        )

    def test_sdk_failure_raises_provider_specific_error(self):
        from ai_services.clients.openai_image_client import (
            OpenAIImageGenerationError,
        )

        sdk_client = MagicMock()
        sdk_client.images.generate.side_effect = RuntimeError("offline failure")
        client = self._client(sdk_client)

        with self.assertRaises(OpenAIImageGenerationError) as raised:
            client.generate_image("A product photograph")

        self.assertIn("OpenAI image generation failed", str(raised.exception))

    def test_invalid_base64_raises_provider_specific_error(self):
        from ai_services.clients.openai_image_client import (
            OpenAIImageGenerationError,
        )

        sdk_client = MagicMock()
        sdk_client.images.generate.return_value = SimpleNamespace(
            data=[SimpleNamespace(b64_json="not valid base64!")]
        )
        client = self._client(sdk_client)

        with self.assertRaises(OpenAIImageGenerationError):
            client.generate_image("A product photograph")


class CloudflareImageClientCompatibilityTests(SimpleTestCase):
    def _client(self):
        from ai_services.clients.cloudflare_image_client import (
            CloudflareImageClient,
        )

        with patch.dict(
            os.environ,
            {
                "CLOUDFLARE_ACCOUNT_ID": "test-account",
                "CLOUDFLARE_API_TOKEN": "test-token",
                "CLOUDFLARE_IMAGE_MODEL": (
                    "@cf/black-forest-labs/flux-2-klein-9b"
                ),
            },
        ):
            return CloudflareImageClient()

    def test_default_generate_image_uses_flux_multipart(self):
        client = self._client()
        png = _png_bytes()
        response = MagicMock()
        response.ok = True
        response.status_code = 200
        response.headers = {"Content-Type": "application/json"}
        response.content = b"{}"
        response.json.return_value = {
            "success": True,
            "result": {
                "image": base64.b64encode(png).decode("ascii"),
            },
        }
        with patch(
            "ai_services.clients.cloudflare_image_client.requests.post",
            return_value=response,
        ) as mocked_post:
            result = client.generate_image("a perfume bottle")
        self.assertEqual(result, png)
        mocked_post.assert_called_once()
        kwargs = mocked_post.call_args.kwargs
        url = mocked_post.call_args.args[0]
        self.assertIn(
            "@cf/black-forest-labs/flux-2-klein-9b",
            url,
        )
        self.assertIn("files", kwargs)
        self.assertNotIn("json", kwargs)
        self.assertEqual(
            kwargs["files"]["prompt"],
            (None, "a perfume bottle"),
        )

    def test_optional_model_uses_json_for_sdxl_lightning(self):
        client = self._client()
        png = _png_bytes()
        response = MagicMock()
        response.ok = True
        response.status_code = 200
        response.headers = {"Content-Type": "image/png"}
        response.content = png
        with patch(
            "ai_services.clients.cloudflare_image_client.requests.post",
            return_value=response,
        ) as mocked_post:
            result = client.generate_image(
                "a perfume bottle",
                model="@cf/bytedance/stable-diffusion-xl-lightning",
            )
        self.assertEqual(result, png)
        kwargs = mocked_post.call_args.kwargs
        url = mocked_post.call_args.args[0]
        self.assertIn(
            "@cf/bytedance/stable-diffusion-xl-lightning",
            url,
        )
        self.assertIn("json", kwargs)
        self.assertNotIn("files", kwargs)
        self.assertEqual(kwargs["json"]["prompt"], "a perfume bottle")
        self.assertNotIn("negative_prompt", kwargs["json"])

    def test_dreamshaper_sends_negative_prompt_when_provided(self):
        client = self._client()
        png = _png_bytes()
        response = MagicMock()
        response.ok = True
        response.status_code = 200
        response.headers = {"Content-Type": "image/png"}
        response.content = png
        with patch(
            "ai_services.clients.cloudflare_image_client.requests.post",
            return_value=response,
        ) as mocked_post:
            client.generate_image(
                "a perfume bottle",
                model="@cf/lykon/dreamshaper-8-lcm",
                negative_prompt="text, letters, typography",
            )
        payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(
            payload["negative_prompt"],
            "text, letters, typography",
        )
