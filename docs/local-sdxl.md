# Connecting local SDXL

Gemini remains the text provider. SDXL is an optional, separate local HTTP service called only by FastAPI after panel descriptions exist. Disabled by default, it needs no API key. No paid image API, model download, GPU package installation or automatic provider switching occurs in StoryVerse.

## AUTOMATIC1111

1. Install [AUTOMATIC1111](https://github.com/AUTOMATIC1111/stable-diffusion-webui#installation-and-running) separately, using its supported Python/CUDA dependencies. Do not install its GPU dependencies into StoryVerse's backend virtualenv.
2. Obtain a compatible SDXL base checkpoint, such as [SDXL base 1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0), under its license. Place it in the runtime's `models/Stable-diffusion/` directory and select it in the runtime. StoryVerse checks the selected checkpoint name; it never downloads or switches weights.
3. Start the runtime on loopback with its API and SDXL memory optimization. On Windows, add this to the runtime's `webui-user.bat`, preserving any other intentional settings:

   ```bat
   set COMMANDLINE_ARGS=--api --medvram-sdxl
   ```

   Launch `webui-user.bat`. Use the runtime's `/docs` page to inspect its actual installed API. Consult its [API guide](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API) and [command-line reference](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/Command-Line-Arguments-and-Settings). Runtime versions may differ.

4. Set `backend/.env`:

   ```dotenv
   SDXL_ENABLED=true
   SDXL_API_FLAVOR=a1111
   SDXL_BASE_URL=http://127.0.0.1:7860
   SDXL_MODEL=sd_xl_base_1.0.safetensors
   SDXL_WIDTH=768
   SDXL_HEIGHT=768
   SDXL_STEPS=20
   SDXL_CFG_SCALE=6
   SDXL_SAMPLER=DPM++ 2M
   SDXL_TIMEOUT_SECONDS=120
   SDXL_SEED=42
   ```

5. Apply migration `202610170003_local_sdxl.sql` if using Supabase. Configure its backend service-role key for protected job RPCs; normal storage writes still use the caller's JWT. Restart FastAPI. Generate a Gemini chapter, review its text, and choose a panel's **Generate image** action.

The adapter checks `/sdapi/v1/options` for the selected checkpoint and `/sdapi/v1/progress` for busy state, then posts `/sdapi/v1/txt2img`. It expects exactly one base64 PNG. It disables high-resolution/refiner passes and server-side image saving. The runtime can retain its own request history; configure that separately if needed.

## ComfyUI native API

1. Install [ComfyUI locally](https://docs.comfy.org/installation/manual_install) in its own supported environment or use its Windows portable distribution. StoryVerse adds no ComfyUI dependency, custom nodes, GPU libraries or weights.
2. Place an SDXL base checkpoint, including its CLIP/VAE, in ComfyUI's `models/checkpoints/`. Set `SDXL_MODEL` to its exact listed filename (including a relative subfolder if used). Unlike AUTOMATIC1111's selected-checkpoint check, this workflow explicitly loads the configured **already installed** checkpoint. No download, refiner or fallback model is requested.
3. For a manual installation, start from the ComfyUI directory with its own Python:

   ```powershell
   python main.py --listen 127.0.0.1 --port 8188 --lowvram --preview-method none
   ```

   For Windows portable, pass equivalent arguments to the bundled Python's `ComfyUI/main.py` invocation. Follow ComfyUI's [startup flags](https://docs.comfy.org/development/comfyui-server/startup-flags). Memory-management behavior depends on version: recent dynamic VRAM management may ignore `--lowvram`; use the installed runtime's `--help` and [CLI source](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/cli_args.py). Offloading belongs to the runtime, not the HTTP request. Do not use high-VRAM/GPU-only settings on a 6 GB GPU.

4. Configure `backend/.env` and restart FastAPI:

   ```dotenv
   SDXL_ENABLED=true
   SDXL_API_FLAVOR=comfyui
   SDXL_BASE_URL=http://127.0.0.1:8188
   SDXL_MODEL=sd_xl_base_1.0.safetensors
   SDXL_WIDTH=768
   SDXL_HEIGHT=768
   SDXL_STEPS=20
   SDXL_CFG_SCALE=6
   SDXL_SEED=42
   SDXL_TIMEOUT_SECONDS=120
   COMFYUI_SAMPLER=dpmpp_2m
   COMFYUI_SCHEDULER=karras
   COMFYUI_POLL_INTERVAL_SECONDS=1
   ```

   `SDXL_SAMPLER` continues to configure AUTOMATIC1111/generic; ComfyUI uses its own native sampler/scheduler names above. The poll interval supports 0.1–5 seconds. Total submission, polling and download time is bounded by the existing SDXL timeout. Keep image generation optional by leaving `SDXL_ENABLED=false` until ready.

5. Use the existing Studio **Generate image**/**Regenerate image** controls. No frontend changes, new migration or exported workflow file is needed. Existing Supabase installations still require migration 003 and the backend service role for image jobs.

The native adapter checks `GET /queue` and refuses new work while any execution is running or pending. It submits one API-format workflow to `POST /prompt`, then polls only its returned execution ID at `GET /history/{prompt_id}`. After successful completion it retrieves the single output PNG using `GET /view?filename=...&subfolder=...&type=temp`. These are ComfyUI's [self-hosted API routes](https://docs.comfy.org/development/comfyui-server/comms_routes), independent of its cloud API.

The included graph contains only built-in nodes: `CheckpointLoaderSimple`, positive/negative `CLIPTextEncode`, `EmptyLatentImage`, `KSampler`, `VAEDecodeTiled` and `PreviewImage`. It renders one 768×768 latent at 20 steps by default, uses 512px VAE tiles, and has no refiner, upscale pass, additional sampler or cloud/partner node. Runtime compatibility with those core nodes is required. Arbitrary custom workflows are not accepted through this adapter. Unsupported checkpoints, sampler names or nodes cause a clear failure; check ComfyUI's local console.

The PNG goes through the existing validation, owner-private upload, versioning and explicit publication flow. Metadata records `api_flavor: comfyui`, the execution ID, sampler/scheduler and workflow version. Paths returned by ComfyUI are used only as validated `/view` query parameters; no arbitrary URL is fetched. ComfyUI itself retains history and temporary preview files outside StoryVerse's storage permissions—keep it on loopback and manage those files separately. Do not expose its unauthenticated API publicly.

Failed/interrupted executions never become generated images. A timeout does not resubmit, clear the queue or interrupt unrelated jobs: ComfyUI may still be rendering. Wait for its queue to become idle before an explicit retry. Runtime clients can race the queue check, so reserve this runtime for StoryVerse or serialize other clients too. The existing database image lock still spans submission, polling and download across StoryVerse workers.

**Real 768×768 SDXL generation was verified on the local RTX 4050/6 GB setup on 17 October 2026**, both through the opt-in test (20.17 seconds) and Studio's actual panel button (20.29 seconds). Studio used real Gemini panel descriptions and saved a separate owner-private version. No OOM occurred; maximum sampled overall GPU usage was 5,513/6,141 MiB, not an exact instantaneous peak. See [actual results and remaining checks](live-comfyui-validation.md). These remain conservative starting settings, not a universal performance guarantee. Use the opt-in live test below for your configuration. If a first model load is slow, raise the timeout up to 300 seconds; if memory is insufficient, try 512×512 and adjust runtime offloading. Default automated tests mock ComfyUI; the explicit live test does not.

## Memory and concurrency

The default 768×768, 20-step, batch-one request is a conservative starting point for an RTX 4050. **Two actual inference runs passed on this machine; exact instantaneous peak VRAM remains unmeasured.** Sizes must be multiples of 64 between 256 and 1024. Try 512×512 if necessary. Keep other GPU workloads idle; raising the timeout up to 300 seconds changes waiting time, not available VRAM.

Memory offload/attention/precision settings belong to your runtime. For another implementation, review its own guidance, such as [Diffusers memory optimization](https://huggingface.co/docs/diffusers/en/optimization/memory). StoryVerse's `low_vram` hint cannot enforce a runtime's memory behavior. Do not enable automatic model/refiner switching or extra batch jobs.

One active image reservation is allowed across API workers/users. The runtime must also serialize work from other clients. Runtime busy checks reduce overlap but cannot prevent unrelated clients from racing those checks. No automatic image retry occurs. A timed-out HTTP request may still be running on the GPU: leave it running until idle or stop it in the runtime, then explicitly retry. Descriptions and previous images remain available.

## Generic local inference endpoint

Set `SDXL_API_FLAVOR=generic` and `SDXL_BASE_URL=http://127.0.0.1:8002` for a service implementing this contract. This is an adapter contract, **not an included GPU runtime**. For ComfyUI's native API, choose `comfyui` above rather than `generic`.

`GET /health` must return:

```json
{"family":"sdxl","model":"sd_xl_base_1.0.safetensors","busy":false}
```

`POST /generate` receives:

```json
{
  "model":"sd_xl_base_1.0.safetensors",
  "prompt":"Comic book illustration...chapter panel and established character appearance...",
  "negative_prompt":"blurry, low quality, watermark, text, logo, distorted anatomy",
  "width":768,"height":768,"steps":20,"cfg_scale":6,
  "sampler_name":"DPM++ 2M","seed":42,
  "batch_size":1,"n_iter":1,"enable_hr":false,
  "refiner_checkpoint":"None","save_images":false,"send_images":true,"low_vram":true
}
```

Return `{"images":["BASE64_ENCODED_PNG"]}` (one image, not a URL). An optional `data:image/png;base64,` prefix is accepted. Use PNG dimensions no larger than the request; binary image limit is 10 MiB, total HTTP response limit 16 MiB, additionally bounded by `MAX_UPLOAD_BYTES`. Non-PNG, malformed, oversized and multi-image responses are rejected. A service should return a failure without invoking a cloud provider when offline, busy or out of memory.

The endpoint origin must be loopback (`127.0.0.1`, `localhost` or `::1`), without credentials, query or path. Redirects and environment proxy routing are disabled. FastAPI and the runtime must share the same host/network namespace; a deployed cloud FastAPI cannot reach a laptop's loopback. This adapter does not support remote endpoints or endpoint authentication.

## Stored data and fallback

Prompts combine the AI chapter's panel description, scene/camera and matching fictional character appearance notes. No account details, secrets, uploads or complete private-draft history go to SDXL. The panel retains its description/caption and stores upload ID, model, seed, dimensions, steps, sampler, configuration, hashes and fixture provenance. Image bytes use the existing local-file/Supabase private bucket flow.

Every successful image generation creates a new private draft version. Other panels, reviewed text and manual uploads are preserved. Description regeneration drops that panel's outdated image only in the new version. Explicit approval and version-checked publication make only referenced images public in the same transaction. Unused older images remain private. A storage write followed by a stale-result rejection may leave a private orphan; automatic cleanup is not included.

With SDXL disabled, buttons are hidden and labeled descriptions remain. With it enabled but unavailable, an explicit error preserves the saved draft and images; users can publish descriptions or retry later. Placeholder descriptions are never labeled generated artwork. Automated fixture PNGs are visibly labeled **“Mocked SDXL test image · No local inference.”**

## Live verification

Automated tests mock all three adapters, including native ComfyUI submission/history/view responses, failures, image validation, versioning, storage and publication. No live runtime or model call is needed. Configuration in `/api/health` is not a successful runtime probe; it reports the configured `api_flavor` and `runtime_status: "not_verified"`.

After installing/configuring the runtime, from `backend/` run:

```powershell
$env:STORYVERSE_LIVE_SDXL_TESTS="1"
.\.venv\Scripts\python.exe -m pytest tests/test_sdxl_live.py -q
Remove-Item Env:STORYVERSE_LIVE_SDXL_TESTS
```

This explicitly performs one real GPU render with whichever `SDXL_API_FLAVOR` you configured (including `comfyui`) and validates its PNG/metadata without calling Gemini. It does not save a StoryVerse chapter. Then manually exercise Studio image preview, regeneration and approved publication to test your full runtime/storage setup. Record latency, image quality and peak VRAM separately; a returned PNG alone does not prove those properties. Keep the live flag unset for normal tests.
