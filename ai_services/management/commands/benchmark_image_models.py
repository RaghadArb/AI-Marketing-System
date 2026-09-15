import json
import re
import time
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from ai_services.clients.cloudflare_image_client import (
    CloudflareImageClient,
)


SHARED_PROMPT = """
Create a premium commercial advertising photograph for a luxury perfume bottle.

The perfume bottle is centered on a glossy black reflective surface.

Use a dark cinematic studio background with elegant warm gold lighting,
subtle gold particles in the air, controlled reflections, premium product
photography, realistic glass and liquid materials, soft dramatic shadows,
high-end advertising aesthetics, balanced composition, and strong visual focus
on the bottle.

Color palette: black, deep charcoal, warm metallic gold.

Mood: luxurious, elegant, sophisticated, cinematic.

Square social-media advertising composition.

Do not add text, letters, numbers, logos, trademarks, labels, watermarks,
captions, headlines, CTA buttons, or typography.

The image must be purely visual commercial product photography.
""".strip()

DREAMSHAPER_NEGATIVE_PROMPT = (
    "text, letters, typography, logo, watermark, "
    "distorted product, blurry image"
)

BENCHMARK_MODELS = (
    {
        "display_name": "FLUX.2 Klein 9B",
        "model_id": "@cf/black-forest-labs/flux-2-klein-9b",
        "filename": "flux2_klein_9b.png",
        "negative_prompt": None,
    },
    {
        "display_name": "SDXL Lightning",
        "model_id": "@cf/bytedance/stable-diffusion-xl-lightning",
        "filename": "sdxl_lightning.png",
        "negative_prompt": None,
    },
    {
        "display_name": "DreamShaper 8 LCM",
        "model_id": "@cf/lykon/dreamshaper-8-lcm",
        "filename": "dreamshaper_8_lcm.png",
        "negative_prompt": DREAMSHAPER_NEGATIVE_PROMPT,
    },
)


def _http_status(message):
    match = re.search(r"HTTP\s+(\d+)", str(message), flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _error_code(message):
    match = re.search(r"['\"]code['\"]\s*:\s*(\d+)", str(message))
    if match:
        return int(match.group(1))
    return None


def _as_png_bytes(image_bytes):
    image = Image.open(BytesIO(image_bytes))
    converted = image.convert("RGB") if image.mode not in ("RGB", "RGBA") else image
    buffer = BytesIO()
    converted.save(buffer, format="PNG")
    return buffer.getvalue(), converted.size


class Command(BaseCommand):
    help = (
        "Generate one perfume-ad image from each of three Cloudflare "
        "Workers AI models for an isolated visual benchmark. "
        "Does not change Content Studio."
    )

    def handle(self, *args, **options):
        out_dir = Path(settings.MEDIA_ROOT) / "image_model_benchmark"
        out_dir.mkdir(parents=True, exist_ok=True)
        client = CloudflareImageClient()
        results = []

        self.stdout.write("IMAGE MODEL BENCHMARK")
        self.stdout.write("")

        for spec in BENCHMARK_MODELS:
            started = time.perf_counter()
            record = {
                "display_name": spec["display_name"],
                "model_id": spec["model_id"],
                "status": "failure",
                "generation_time_seconds": None,
                "http_status": None,
                "error_code": None,
                "error": None,
                "file": None,
                "image_width": None,
                "image_height": None,
            }
            try:
                kwargs = {
                    "prompt": SHARED_PROMPT,
                    "width": 1024,
                    "height": 1024,
                    "model": spec["model_id"],
                }
                if spec["negative_prompt"]:
                    kwargs["negative_prompt"] = spec["negative_prompt"]
                image_bytes = client.generate_image(**kwargs)
                png_bytes, size = _as_png_bytes(image_bytes)
                dest = out_dir / spec["filename"]
                dest.write_bytes(png_bytes)
                record["status"] = "success"
                record["file"] = str(dest)
                record["image_width"] = size[0]
                record["image_height"] = size[1]
            except Exception as exc:
                message = str(exc)
                record["error"] = message
                record["http_status"] = _http_status(message)
                record["error_code"] = _error_code(message)
            record["generation_time_seconds"] = round(
                time.perf_counter() - started,
                3,
            )
            results.append(record)
            self._print_record(record)

        report_path = out_dir / "benchmark_results.json"
        report_path.write_text(
            json.dumps(
                {
                    "prompt": SHARED_PROMPT,
                    "results": results,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        self.stdout.write(f"Saved: {report_path}")

    def _print_record(self, record):
        self.stdout.write(record["display_name"])
        self.stdout.write(f"Model ID: {record['model_id']}")
        self.stdout.write(f"Status: {record['status']}")
        self.stdout.write(f"Time: {record['generation_time_seconds']}")
        self.stdout.write(f"File: {record['file'] or ''}")
        self.stdout.write(f"Error: {record['error'] or ''}")
        self.stdout.write("")
