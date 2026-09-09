import base64
import os

import requests
from dotenv import load_dotenv


load_dotenv()


class CloudflareImageClient:
    """
    Cloudflare Workers AI client for IMAGE generation only.

    Model:
        @cf/black-forest-labs/flux-2-klein-9b

    FLUX.2 Klein 9B expects multipart/form-data input and returns
    the generated image as Base64 in result.image.
    """

    DEFAULT_MODEL = "@cf/black-forest-labs/flux-2-klein-9b"

    def __init__(self):
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.model = os.getenv(
            "CLOUDFLARE_IMAGE_MODEL",
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

    def generate_image(
        self,
        prompt,
        width=1024,
        height=1024,
        guidance=None,
        seed=None,
        reference_image=None,
        reference_filename="input_image_0.png",
        reference_content_type="image/png",
    ):
        if not prompt or not str(prompt).strip():
            raise ValueError("Image prompt cannot be empty.")

        if not 256 <= int(width) <= 1920:
            raise ValueError("width must be between 256 and 1920.")

        if not 256 <= int(height) <= 1920:
            raise ValueError("height must be between 256 and 1920.")

        # Using files=(None, value) makes requests construct
        # a proper multipart/form-data request including its boundary.
        multipart = {
            "prompt": (None, str(prompt).strip()),
            "width": (None, str(int(width))),
            "height": (None, str(int(height))),
        }

        if guidance is not None:
            multipart["guidance"] = (
                None,
                str(guidance),
            )

        if seed is not None:
            multipart["seed"] = (
                None,
                str(int(seed)),
            )

        if reference_image:
            multipart["input_image_0"] = (
                reference_filename or "input_image_0.png",
                reference_image,
                reference_content_type or "image/png",
            )

        try:
            response = requests.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                },
                files=multipart,
                timeout=180,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Cloudflare image generation connection failed: {exc}"
            ) from exc

        if not response.ok:
            try:
                details = response.json()
            except ValueError:
                details = response.text

            raise RuntimeError(
                "Cloudflare FLUX image generation failed. "
                f"HTTP {response.status_code}: {details}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Cloudflare FLUX returned invalid JSON."
            ) from exc

        if not payload.get("success", True):
            raise RuntimeError(
                "Cloudflare FLUX image generation failed: "
                f"{payload.get('errors', payload)}"
            )

        result = payload.get("result", {})

        if not isinstance(result, dict):
            raise RuntimeError(
                "Cloudflare FLUX returned an unsupported result format."
            )

        image_base64 = result.get("image")

        if not image_base64:
            raise RuntimeError(
                "Cloudflare FLUX response did not contain result.image."
            )

        if image_base64.startswith("data:image"):
            image_base64 = image_base64.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(
                image_base64,
                validate=False,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not decode Cloudflare FLUX image: {exc}"
            ) from exc

        if not image_bytes:
            raise RuntimeError(
                "Cloudflare FLUX returned an empty image."
            )

        return image_bytes
