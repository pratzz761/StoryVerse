"""Native ComfyUI SDXL workflow; HTTP/timeout/locking remain in LocalSDXLProvider."""
import asyncio
from uuid import UUID, uuid4
from .providers import GenerationError


OUTPUT_NODE = "7"


def sdxl_workflow(settings, prompt, seed):
    """API-format graph using only built-in nodes, one base model and one latent."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": settings.sdxl_model}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": settings.sdxl_negative_prompt, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {
            "width": settings.sdxl_width, "height": settings.sdxl_height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
            "seed": seed, "steps": settings.sdxl_steps, "cfg": settings.sdxl_cfg_scale, "denoise": 1.0,
            "sampler_name": settings.comfyui_sampler, "scheduler": settings.comfyui_scheduler}},
        "6": {"class_type": "VAEDecodeTiled", "inputs": {
            "samples": ["5", 0], "vae": ["1", 2], "tile_size": 512, "overlap": 64,
            "temporal_size": 64, "temporal_overlap": 8}},
        OUTPUT_NODE: {"class_type": "PreviewImage", "inputs": {"images": ["6", 0]}},
    }


def image_reference(value):
    """Only a local image descriptor from our output node may reach /view."""
    filename, subfolder, kind = value["filename"], value.get("subfolder", ""), value["type"]
    if (not isinstance(filename, str) or not filename or len(filename) > 255
        or any(c in filename for c in ("/", "\\", ":", "\x00")) or filename in {".", ".."}
        or not isinstance(subfolder, str) or len(subfolder) > 500
        or any(c in subfolder for c in ("\\", ":", "\x00"))
        or (subfolder and any(p in {"", ".", ".."} for p in subfolder.split("/")))
        or kind not in {"temp", "output"}):
        raise GenerationError("invalid_image", "ComfyUI returned an unsupported local image reference. Your previous panel is preserved.")
    return {"filename": filename, "subfolder": subfolder, "type": kind}


class ComfyUIAdapter:
    def __init__(self, settings, request_json, request_bytes):
        self.settings = settings
        self.json = request_json
        self.bytes = request_bytes

    async def generate(self, prompt, seed):
        # Includes jobs from other clients, not only this application's DB leases.
        queue = await self.json("GET", "/queue")
        if not isinstance(queue.get("queue_running"), list) or not isinstance(queue.get("queue_pending"), list):
            raise GenerationError("sdxl_unavailable", "ComfyUI returned an unsupported queue response.", 503)
        if queue["queue_running"] or queue["queue_pending"]:
            raise GenerationError("sdxl_busy", "ComfyUI is busy. Wait until its queue is idle before retrying.", 409)
        submitted = await self.json("POST", "/prompt", json={
            "prompt": sdxl_workflow(self.settings, prompt, seed), "client_id": str(uuid4())})
        if submitted.get("error") or submitted.get("node_errors"):
            raise GenerationError("sdxl_workflow_invalid", "ComfyUI rejected the SDXL workflow. Check the checkpoint, sampler and built-in nodes.", 503)
        prompt_id = submitted.get("prompt_id")
        try:
            if not isinstance(prompt_id, str) or str(UUID(prompt_id)) != prompt_id:
                raise ValueError("Invalid prompt ID")
        except ValueError as exc:
            raise GenerationError("sdxl_workflow_invalid", "ComfyUI did not return a valid execution ID.", 503) from exc

        # The caller's overall timeout bounds queueing, polling and image transfer.
        # Polling reads status; it never submits the workflow again.
        while True:
            history = await self.json("GET", f"/history/{prompt_id}")
            entry = history.get(prompt_id)
            if entry is not None:
                status = entry["status"]
                failed = status.get("status_str") == "error" or any(
                    message[0] in {"execution_error", "execution_interrupted"}
                    for message in status.get("messages", []))
                if failed:
                    # Raw execution errors can contain prompts, paths and traces.
                    raise GenerationError("sdxl_execution_failed", "ComfyUI could not render this panel. Check its local console (including VRAM), then retry. Your saved draft is safe.", 503)
                if status.get("completed") is True:
                    if status.get("status_str") != "success":
                        raise GenerationError("invalid_image", "ComfyUI returned an unsupported completion status.")
                    images = entry.get("outputs", {}).get(OUTPUT_NODE, {}).get("images", [])
                    if not isinstance(images, list) or len(images) != 1:
                        raise GenerationError("invalid_image", "ComfyUI must return exactly one image from the panel output node.")
                    params = image_reference(images[0])
                    content = await self.bytes("GET", "/view", params=params)
                    return content, {"comfyui_prompt_id": prompt_id, "scheduler": self.settings.comfyui_scheduler,
                        "vae_decode": "tiled", "workflow_version": 1}
            await asyncio.sleep(self.settings.comfyui_poll_interval_seconds)
