"""Local-only SDXL adapter. No weights, GPU libraries, paid APIs or downloads."""
import asyncio
import base64
import hashlib
import io
import json
from urllib.parse import urlsplit
import httpx
from PIL import Image, UnidentifiedImageError
from .providers import GenerationError, ImageProvider, ImageResult
from .comfyui import ComfyUIAdapter

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024


LocalImage = ImageResult


def validate_png(content, max_width=1024, max_height=1024):
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise GenerationError("invalid_image", "SDXL returned an empty or oversized image. The previous panel is preserved.")
    try:
        with Image.open(io.BytesIO(content)) as picture:
            if picture.format != "PNG" or not (0 < picture.width <= max_width and 0 < picture.height <= max_height):
                raise ValueError("Unexpected image format or size")
            size = picture.size
            picture.verify()
        return size
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise GenerationError("invalid_image", "SDXL returned an invalid PNG or unsupported dimensions. Your previous panel is preserved.") from exc


def local_base_url(value):
    try:
        parsed = urlsplit(value)
        # Force validation of malformed/out-of-range ports before httpx sees it.
        parsed.port
    except ValueError as exc:
        raise GenerationError("invalid_local_endpoint", "SDXL_BASE_URL must be a valid loopback HTTP(S) origin.", 503) from exc
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise GenerationError("invalid_local_endpoint", "SDXL_BASE_URL must be a loopback HTTP(S) origin. Remote and paid image APIs are not supported.", 503)
    return value.rstrip("/")


def panel_prompt(panel, bible):
    names = {name.casefold() for name in panel.get("characters", [])}
    appearances = [{"name": c["name"], "description": c.get("visual_description") or c["description"]} for c in bible.get("characters", []) if c["name"].casefold() in names]
    pieces = ["Comic book illustration, coherent character design, clean linework, cinematic composition, no lettering.",
        panel["description"], f"Location: {panel['location']}. Camera: {panel['camera']}."]
    if appearances:
        pieces.append("Keep established appearances: " + json.dumps(appearances, ensure_ascii=False))
    # No account data, upload bytes, credentials or endpoint URLs enter the prompt.
    return "\n".join(pieces)[:5000]


class LocalSDXLProvider(ImageProvider):
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client
        self.lock = asyncio.Lock()

    async def _bytes(self, method, path, limit=MAX_IMAGE_BYTES, **kwargs):
        async with self.client.stream(method, path, **kwargs) as response:
            if response.is_error or response.is_redirect:
                raise GenerationError("sdxl_unavailable", "Local SDXL is unavailable or rejected this request. Panel descriptions and existing images remain available.", 503)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > limit:
                    raise GenerationError("invalid_image", "The SDXL response exceeded the image-size limit.")
        return bytes(body)

    async def _json(self, method, path, **kwargs):
        body = await self._bytes(method, path, limit=MAX_RESPONSE_BYTES, **kwargs)
        try:
            return json.loads(body)
        except (ValueError, TypeError) as exc:
            raise GenerationError("invalid_image", "The local endpoint returned an invalid image response.") from exc

    async def generate(self, description, appearance_context):
        s = self.settings
        if not s.sdxl_enabled:
            raise GenerationError("images_disabled", "Local SDXL is disabled. Panel descriptions remain available.", 503)
        origin = local_base_url(s.sdxl_base_url)
        if self.lock.locked():
            raise GenerationError("sdxl_busy", "One local image is already generating. Wait before retrying.", 409)
        if self.client is None:
            self.client = httpx.AsyncClient(base_url=origin, timeout=s.sdxl_timeout_seconds,
                trust_env=False, follow_redirects=False)
        prompt = panel_prompt(description, appearance_context.get("bible", {}))
        seed = appearance_context.get("seed", s.sdxl_seed)
        payload = {"prompt": prompt, "negative_prompt": s.sdxl_negative_prompt, "width": s.sdxl_width,
            "height": s.sdxl_height, "steps": s.sdxl_steps, "cfg_scale": s.sdxl_cfg_scale,
            "sampler_name": s.sdxl_sampler, "seed": seed, "batch_size": 1, "n_iter": 1,
            "enable_hr": False, "refiner_checkpoint": "None", "save_images": False, "send_images": True}
        try:
            async with self.lock, asyncio.timeout(s.sdxl_timeout_seconds):
                if s.sdxl_api_flavor == "a1111":
                    options = await self._json("GET", "/sdapi/v1/options")
                    current = options.get("sd_model_checkpoint", "")
                    expected = s.sdxl_model.rsplit(".", 1)[0].casefold()
                    if not expected or expected not in current.casefold():
                        raise GenerationError("sdxl_model_mismatch", "Select the configured SDXL checkpoint in the local runtime before generating. No model was downloaded or switched.", 503)
                    progress = await self._json("GET", "/sdapi/v1/progress", params={"skip_current_image": "true"})
                    if progress.get("state", {}).get("job_count", 0) > 0:
                        raise GenerationError("sdxl_busy", "The local GPU service is busy. Wait before retrying.", 409)
                    data = await self._json("POST", "/sdapi/v1/txt2img", json=payload)
                elif s.sdxl_api_flavor == "generic":
                    health = await self._json("GET", "/health")
                    if health.get("family") != "sdxl" or health.get("model") != s.sdxl_model:
                        raise GenerationError("sdxl_model_mismatch", "The local endpoint must report the configured SDXL model.", 503)
                    if health.get("busy"):
                        raise GenerationError("sdxl_busy", "The local GPU service is busy. Wait before retrying.", 409)
                    data = await self._json("POST", "/generate", json={**payload, "model": s.sdxl_model, "low_vram": True})
                extra = {}
                if s.sdxl_api_flavor == "comfyui":
                    content, extra = await ComfyUIAdapter(s, self._json, self._bytes).generate(prompt, seed)
                else:
                    images = data.get("images", [])
                    if len(images) != 1 or not isinstance(images[0], str):
                        raise GenerationError("invalid_image", "Local SDXL must return exactly one base64 PNG image.")
                    encoded = images[0]
                    if encoded.startswith("data:image/png;base64,"):
                        encoded = encoded.partition(",")[2]
                    try:
                        content = base64.b64decode(encoded, validate=True)
                    except ValueError as exc:
                        raise GenerationError("invalid_image", "Local SDXL returned invalid image encoding.") from exc
                width, height = validate_png(content, s.sdxl_width, s.sdxl_height)
                return LocalImage(content, "image/png", {"provider": "local_sdxl", "model": s.sdxl_model,
                    "width": width, "height": height, "steps": s.sdxl_steps, "cfg_scale": s.sdxl_cfg_scale,
                    "sampler": s.comfyui_sampler if s.sdxl_api_flavor == "comfyui" else s.sdxl_sampler,
                    "seed": seed, "batch_size": 1, "api_flavor": s.sdxl_api_flavor, **extra,
                    "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(), "sha256": hashlib.sha256(content).hexdigest(),
                    "is_test_fixture": bool(getattr(self, "is_test_fixture", False))})
        except GenerationError:
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise GenerationError("sdxl_timeout", "Local SDXL timed out. Descriptions and previous images are preserved. It may still be rendering; wait until the runtime is idle before retrying.", 504) from exc
        except httpx.RequestError as exc:
            raise GenerationError("sdxl_unavailable", "Local SDXL could not be reached. Use the panel descriptions, or start the configured local service and retry.", 503) from exc
        except (AttributeError, KeyError, TypeError, IndexError) as exc:
            raise GenerationError("invalid_image", "The local endpoint returned an unsupported response. Your previous panel is preserved.") from exc

    async def close(self):
        if self.client:
            await self.client.aclose()
