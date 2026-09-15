import base64
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from PIL import Image


def _png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


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
