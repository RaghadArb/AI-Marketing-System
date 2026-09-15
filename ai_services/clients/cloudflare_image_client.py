import base64
import os

import requests
from dotenv import load_dotenv


load_dotenv()


class CloudflareImageClient:
    """
    Cloudflare Workers AI client for IMAGE generation only.

    Default model (production):
        @cf/black-forest-labs/flux-2-klein-9b

    FLUX.2 Klein 9B expects multipart/form-data input and returns
    the generated image as Base64 in result.image.

    generate_image(..., model=...) is optional. Calls without model
    keep the existing default/env model and FLUX request format.
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

        self.url = self._url_for(self.model)

    def _url_for(self, model_id):
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/{model_id}"
        )

    @staticmethod
    def _is_flux_model(model_id):
        return "flux" in str(model_id or "").lower()

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
        model=None,
        negative_prompt=None,
    ):
        if not prompt or not str(prompt).strip():
            raise ValueError("Image prompt cannot be empty.")

        if not 256 <= int(width) <= 1920:
            raise ValueError("width must be between 256 and 1920.")

        if not 256 <= int(height) <= 1920:
            raise ValueError("height must be between 256 and 1920.")

        resolved_model = model or self.model
        url = self._url_for(resolved_model)

        if self._is_flux_model(resolved_model):
            return self._generate_flux_multipart(
                url=url,
                prompt=prompt,
                width=width,
                height=height,
                guidance=guidance,
                seed=seed,
                reference_image=reference_image,
                reference_filename=reference_filename,
                reference_content_type=reference_content_type,
            )

        return self._generate_json_image(
            url=url,
            prompt=prompt,
            width=width,
            height=height,
            guidance=guidance,
            seed=seed,
            negative_prompt=negative_prompt,
        )

    def _generate_flux_multipart(
        self,
        url,
        prompt,
        width,
        height,
        guidance,
        seed,
        reference_image,
        reference_filename,
        reference_content_type,
    ):
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
                url,
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

        return self._parse_image_response(response, flux=True)

    def _generate_json_image(
        self,
        url,
        prompt,
        width,
        height,
        guidance,
        seed,
        negative_prompt,
    ):
        payload = {
            "prompt": str(prompt).strip(),
            "width": int(width),
            "height": int(height),
        }
        if negative_prompt:
            payload["negative_prompt"] = str(negative_prompt).strip()
        if guidance is not None:
            payload["guidance"] = guidance
        if seed is not None:
            payload["seed"] = int(seed)

        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Cloudflare image generation connection failed: {exc}"
            ) from exc

        return self._parse_image_response(response, flux=False)

    @staticmethod
    def _parse_image_response(response, flux=True):
        if flux:
            fail_prefix = "Cloudflare FLUX image generation failed"
            json_error = "Cloudflare FLUX returned invalid JSON."
            success_error = "Cloudflare FLUX image generation failed"
            format_error = (
                "Cloudflare FLUX returned an unsupported result format."
            )
            missing_image = (
                "Cloudflare FLUX response did not contain result.image."
            )
            decode_error = "Could not decode Cloudflare FLUX image"
            empty_image = "Cloudflare FLUX returned an empty image."
            unsupported = (
                "Cloudflare FLUX returned an unsupported image response."
            )
        else:
            fail_prefix = "Cloudflare image generation failed"
            json_error = "Cloudflare image generation returned invalid JSON."
            success_error = "Cloudflare image generation failed"
            format_error = (
                "Cloudflare image generation returned an unsupported "
                "result format."
            )
            missing_image = (
                "Cloudflare image generation response did not contain "
                "result.image."
            )
            decode_error = "Could not decode Cloudflare image"
            empty_image = "Cloudflare image generation returned an empty image."
            unsupported = (
                "Cloudflare image generation returned an unsupported "
                "image response."
            )

        if not response.ok:
            try:
                details = response.json()
            except ValueError:
                details = response.text

            raise RuntimeError(
                f"{fail_prefix}. "
                f"HTTP {response.status_code}: {details}"
            )

        content_type = (
            response.headers.get("Content-Type") or ""
        ).lower()
        raw = response.content or b""

        if (
            "application/json" in content_type
            or raw[:1] in (b"{", b"[")
        ):
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(json_error) from exc

            if not payload.get("success", True):
                raise RuntimeError(
                    f"{success_error}: "
                    f"{payload.get('errors', payload)}"
                )

            result = payload.get("result", {})

            if not isinstance(result, dict):
                raise RuntimeError(format_error)

            image_base64 = result.get("image")

            if not image_base64:
                raise RuntimeError(missing_image)

            if image_base64.startswith("data:image"):
                image_base64 = image_base64.split(",", 1)[1]

            try:
                image_bytes = base64.b64decode(
                    image_base64,
                    validate=False,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"{decode_error}: {exc}"
                ) from exc

            if not image_bytes:
                raise RuntimeError(empty_image)

            return image_bytes

        if raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:2] == b"\xff\xd8":
            return raw

        if "image/" in content_type and raw:
            return raw

        raise RuntimeError(unsupported)
