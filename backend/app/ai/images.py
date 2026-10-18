"""Optional local panel-image workflow; publication remains explicit."""
import copy
import hashlib
import logging
from uuid import uuid4
from fastapi import HTTPException
from .providers import GenerationError
from .schemas import narrative_hash
from .sdxl import LocalSDXLProvider, validate_png, local_base_url

log = logging.getLogger("storyverse.images")


class PanelImageService:
    def __init__(self, settings, repo, provider=None):
        self.settings, self.repo = settings, repo
        self.provider = provider or LocalSDXLProvider(settings)

    def status(self):
        s = self.settings
        enabled = s.sdxl_enabled and (s.app_mode != "supabase" or bool(s.supabase_service_role_key))
        valid_endpoint = True
        try:
            local_base_url(s.sdxl_base_url)
        except GenerationError:
            valid_endpoint = False
        return {"enabled": enabled and valid_endpoint, "provider": "local_sdxl", "api_flavor": s.sdxl_api_flavor, "runtime_status": "not_verified",
            "execution": s.sdxl_execution,
            "mocked": bool(getattr(self.provider, "is_test_fixture", False)), "width": s.sdxl_width,
            "height": s.sdxl_height, "batch_size": 1}

    async def generate(self, token, user_id, draft_id, panel_index, request_id, revision):
        source = await self.repo.generation_source(token, user_id, draft_id)
        if not self.status()["enabled"]:
            raise GenerationError("images_disabled", "Local SDXL is disabled or not configured. Panel descriptions and existing images remain available.", 503)
        panels = source.get("ai_data", {}).get("panels", [])
        if source.get("source") != "ai_generated" or not 0 <= panel_index < len(panels):
            raise HTTPException(422, "Generate chapter panel descriptions before generating an image")
        signature = hashlib.sha256(f"{draft_id}:image:{revision}:{panel_index}".encode()).hexdigest()
        job = await self.repo.reserve_generation(token, user_id, draft_id, request_id, "image", revision, signature, self.settings)
        if job["status"] == "succeeded":
            return {"id": job["result_draft_id"], "replayed": True}
        if job["status"] == "failed":
            raise GenerationError(job.get("error_code") or "image_failed", "That image attempt failed. Descriptions and previous images are intact; use a new request to retry.", 409)
        if not job.get("claimed", True):
            raise HTTPException(409, "This image request is already running")
        try:
            selected = panels[panel_index]
            previous = selected.get("image", {})
            seed = (int(previous.get("seed", self.settings.sdxl_seed + panel_index - 1)) + 1) % 2147483647
            image = await self.provider.generate({k:v for k,v in selected.items() if k != "image"},
                {"bible": source["ai_data"].get("bible_after", {}), "seed": seed})
            width, height = validate_png(image.content, self.settings.sdxl_width, self.settings.sdxl_height)
            if image.mime_type != "image/png" or len(image.content) > self.settings.max_upload_bytes:
                raise GenerationError("invalid_image", "SDXL returned an unsupported image. The previous panel is unchanged.")
            upload = await self.repo.save_upload(token, user_id, str(uuid4()), f"sdxl-panel-{panel_index + 1}.png",
                "image/png", image.content, self.settings.data_dir)
            payload = copy.deepcopy(source["ai_data"])
            payload.update(title=source["title"], narrative=source["narrative"])
            payload["panels"][panel_index]["image"] = {**image.metadata, "upload_id": upload["id"],
                "mime_type": "image/png", "width": width, "height": height, "seed": seed,
                "is_test_fixture": bool(getattr(self.provider, "is_test_fixture", False))}
            payload["memory_revision"] = 0 if payload.get("memory_hash") == narrative_hash(source["title"], source["narrative"]) else -1
            result_id = await self.repo.finish_generation(token, user_id, job["id"], payload,
                {"model": self.settings.sdxl_model, "input_tokens": 0, "output_tokens": 0})
            log.info("image status=success job=%s panel=%s model=%s", job["id"], panel_index, self.settings.sdxl_model)
            return {"id": result_id, "replayed": False}
        except (GenerationError, HTTPException) as exc:
            code = getattr(exc, "code", "image_conflict")
            await self.repo.fail_generation(token, user_id, job["id"], code)
            log.info("image status=failed job=%s code=%s", job["id"], code)
            raise
        except Exception as exc:
            await self.repo.fail_generation(token, user_id, job["id"], "image_failed")
            log.error("image status=failed job=%s code=image_failed", job["id"])
            raise GenerationError("image_failed", "Image generation could not finish. Descriptions and your previous draft are safe.", 503) from exc
