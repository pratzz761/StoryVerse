# Live ComfyUI + SDXL validation

Date: **17 October 2026**. This report records actual local inference, separate from the earlier mocked Phase 2/3 results.

**Follow-up:** [Complete live Studio validation](live-studio-validation.md) now verifies fresh Gemini text/panel descriptions, SDXL image regeneration, restart persistence, edited-chapter analysis, approved publication and both public readers on a dedicated local validation story. Results below are retained for the initial run.

## Endpoint and configuration

Verified HTTP endpoint: **http://127.0.0.1:8188**. `/system_stats`, `/queue` and all required `/object_info/{class}` routes returned HTTP 200. Runtime: **ComfyUI 0.41.3**, PyTorch **2.12.1+cu130**, NVIDIA GeForce **RTX 4050 Laptop GPU**, approximately 6 GB VRAM.

The previously absent ignored `backend/.env` was created for local SDXL, then Gemini was enabled after the operator confirmed an unpaid/free-tier project. Current non-secret configuration:

```dotenv
APP_MODE=demo
AI_MODE=gemini
GEMINI_FREE_TIER_CONFIRMED=true
SDXL_ENABLED=true
SDXL_API_FLAVOR=comfyui
SDXL_BASE_URL=http://127.0.0.1:8188
SDXL_MODEL=sd_xl_base_1.0.safetensors
SDXL_WIDTH=768
SDXL_HEIGHT=768
SDXL_STEPS=20
SDXL_CFG_SCALE=6
SDXL_TIMEOUT_SECONDS=300
SDXL_SEED=42
COMFYUI_SAMPLER=dpmpp_2m
COMFYUI_SCHEDULER=karras
COMFYUI_POLL_INTERVAL_SECONDS=1
```

`GEMINI_API_KEY` is read exclusively from the backend environment/ignored `.env`; its value is omitted here. The configured/default text model is `gemini-3.5-flash-lite`. `APP_MODE=demo` still means durable local SQLite/files with the labeled shared demo persona; it does **not** mean mocked Gemini or SDXL. Hosted Supabase is not enabled in this run.

Batch size is fixed at one in the existing workflow. It has one base checkpoint/sampler, no refiner or upscale pass, and tiled VAE decoding (512px tiles, 64px overlap). Timeout was set to 300 seconds to allow initial model loading; it does not change sampling settings. No ComfyUI installation, model download or runtime restart was performed. Existing AUTOMATIC1111/generic adapters and publication logic were not replaced.

## Compatibility and actual inference

The installed runtime advertises the exact checkpoint `sd_xl_base_1.0.safetensors`, native `dpmpp_2m` sampler and `karras` scheduler. Required inputs, enum values and connection types were checked against the installed node definitions for `CheckpointLoaderSimple`, `CLIPTextEncode`, `EmptyLatentImage`, `KSampler`, `VAEDecodeTiled` and `PreviewImage`.

Executed from `backend/`:

```powershell
$env:STORYVERSE_LIVE_SDXL_TESTS="1"
.\.venv\Scripts\python.exe -m pytest tests/test_sdxl_live.py -q --durations=1
```

Result: **1 passed**, **20.17 seconds** for the test call (**21.24 seconds** for the pytest invocation). ComfyUI's execution timestamps indicate **18.877 seconds** between execution start and success. This run used the existing `LocalSDXLProvider` and native ComfyUI adapter with no injected provider, mocked HTTP transport or paid API.

Execution ID: `aba6a513-aad7-42d8-bc8b-f8a97344417a`. The successful history graph was compared with the exact submitted live-test workflow before retrieving its output. The PNG is **768×768**, **1,301,337 bytes**, and was validated with the existing Pillow/size checks and visually inspected. It depicts the requested comic-style traveler on a woodland bridge.

SHA-256: `2f187847f243e8e76a6d54c6c91f3c4c570766a83c8b731ab5586a378b8dc929`.

Artifacts (ignored local data, not credentials):

- `backend/data/live-validation/aba6a513-aad7-42d8-bc8b-f8a97344417a/sdxl-live-panel.png`
- `result.json`: execution/settings/timing/hash evidence.
- `preflight.json`: installed runtime/node compatibility evidence.
- `storage.json`: real API/upload/disk round-trip evidence.

## Storage and application checks

FastAPI started at **http://127.0.0.1:8000**, and production Next.js started at **http://127.0.0.1:3000**. Both responded successfully. Browser checks loaded Explore and Continue Story through the real same-origin API proxy. Health reports local ComfyUI configured, 768×768, batch one and `mocked: false`.

The actual generated PNG was submitted to the existing `POST /api/uploads` route, saved as owner-private SQLite/upload metadata and a local file, then retrieved byte-for-byte through the API. Upload ID: `f5ad8ce8-43e2-48e7-acea-d4fe5c68d55f`. Stored file: `backend/data/uploads/f5ad8ce8-43e2-48e7-acea-d4fe5c68d55f`. `is_public` remained **false**. Existing stories/drafts were not overwritten, and no chapter was published.

### Actual Studio text → image → private version

**Verified through the real UI, without route interception or injected providers.** Initially no draft/key existed. After the operator configured a key and explicitly confirmed an unpaid project, Gemini was enabled and FastAPI restarted. Sandbox outbound restrictions initially blocked Google; the validation backend was restarted with network permission. A second real failure exposed Gemini rejecting the chapter's combination of nested array bounds with HTTP 400 `INVALID_ARGUMENT`.

A targeted provider compatibility fix sends those array bounds as descriptive guidance instead of `minItems`/`maxItems` grammar constraints. Every result still passes the original strict Pydantic validation, including array/string bounds, extra-field rejection and continuity validation. No model switch, paid fallback, or retry-to-demo was added. The failure was reproduced with the original schema; otherwise identical requests succeeded with only the array bounds removed. Google's [structured-output limitations](https://ai.google.dev/gemini-api/docs/generate-content/structured-output#limitations) describe rejection of complex schemas.

Using Studio's **Retry AI generation** action created real Gemini draft `db205d13-f999-43ac-89e8-ab3f3c5f0396`, titled **Chapter 4: The Bridge of Dried Leaves**, from the saved contributor idea. It contains two panel descriptions, `provider: gemini`, `model: gemini-3.5-flash-lite` and `is_test_fixture: false`. The durable job records 1,173 input and 1,057 output tokens. The original contribution/draft remains available. This was not imported diagnostic text or a fabricated AI result.

Studio's **Generate panel 1 image → Generate image locally** action then returned HTTP 200 in **20.292 seconds**. ComfyUI's own execution interval was **18.359 seconds**. It created a new private draft `b94ebf4f-0af8-4d4f-8ba1-bde80594d73b`, linked to the previous draft, with real image metadata:

- ComfyUI execution: `35fe31d7-b0f8-4851-9cea-a137dd1179bc`.
- Private upload: `3d8f3bb6-e272-48d0-acd3-6b6b24c7fd50`.
- PNG: **768×768**, **1,236,952 bytes**, SHA-256 `075c9b3170052f1932d32be8e7fc6b068d9fd621df66b2b6a7c243a70b1b0e91`.
- Metadata: `api_flavor: comfyui`, base checkpoint, 20 steps, seed 42, batch one, tiled VAE, prompt hash and `is_test_fixture: false`.

The saved upload file and frontend/API download match the metadata hash. The image loads in Studio with natural width 768 and **Generated locally with SDXL** labeling. The prior draft, title/narrative and unselected panel description remain intact. Playwright checked the real Studio at 1440px desktop and 390px mobile widths, including no horizontal overflow. Direct SQLite inspection confirmed owner matching, `is_public: false`, story version **3**, and the original **three published chapters**. No chapter was approved or published during live validation.

Additional ignored artifacts under `backend/data/live-validation/`:

- `studio-text-result.json`, `studio-image-result.json`, `studio-storage-result.json`.
- `studio-real-panel.png`, `studio-real-desktop.png`, `studio-real-mobile.png`, `studio-text-live.png`.
- `studio-browser.mjs`: actual browser validation script; no mocks. It performs generation when executed, so it is not part of the default suite.

Visual inspection confirms real comic artwork, but the generated panel omits Elara and the fox's spectacles from its description. Inference/storage success does not prove prompt fidelity or character consistency; review/regeneration remains necessary. Panel two deliberately remains a labeled description-only placeholder.

`/api/health` deliberately continues to report `runtime_status: "not_verified"`: that field is a static configuration label, not a persisted benchmark result. The successful inference evidence is recorded here rather than inferred from configuration alone.

## GPU memory

Both live workflows completed with **no CUDA out-of-memory or execution error**. A post-test `nvidia-smi` sample reported **4,783 MiB used of 6,141 MiB**. During Studio generation, 20 approximately one-second samples recorded a maximum **5,513 MiB used of 6,141 MiB** (628 MiB remaining). This is sampled overall GPU usage, not the exact instantaneous peak or exclusive ComfyUI allocation. These results verify these local runs, not every RTX 4050 workflow or future memory load.

## Regression checks and credentials

After the provider fix, the backend suite completed with **95 passed, 3 skipped** using live-test opt-ins explicitly disabled. Five additional regression cases cover local enforcement of collection bounds despite the portable provider schema and preservation of schema property names/descriptions. The three default skips remain live Gemini, live SDXL and hosted Supabase; default skips do not negate separately executed live tests.

The existing live Gemini test was explicitly enabled with `STORYVERSE_LIVE_GEMINI_TESTS=1`: **1 passed**, **7.28 seconds** test-call duration (**7.92 seconds** pytest duration). It used the real configured key/model and original strict chapter validator. A pytest cache permission warning did not affect that test. The live SDXL test separately passed as recorded above.

Further regression results:

| Check | Result | Integration scope |
| --- | --- | --- |
| Backend `pytest -q` | **95 passed, 3 skipped**, exit 0 | Real local persistence; provider calls mocked; live opt-ins disabled |
| Opt-in SDXL test | **1 passed**, 20.17s call | Real local ComfyUI/SDXL, validated PNG |
| Opt-in Gemini test | **1 passed**, 7.28s call | Real unpaid-project key and model, strict chapter validation |
| Actual Studio browser journey | **Passed**, desktop and mobile | Real Gemini draft, real SDXL panel, private saved version, previous draft preserved |
| `npm.cmd test` | **14 passed (4.4m)**, exit 0 | Isolated desktop/mobile journeys, explicitly mocked providers |
| `npm.cmd run test:db` | **Passed** | All four actual migrations in PGlite, authorization/publication/storage contracts; hosted Auth/Storage stand-ins |
| `npm.cmd run typecheck` | **Passed**, exit 0 | TypeScript |
| `npm.cmd run build` | **Passed**, exit 0 | Next.js production routes/build |

The browser regression assertions all passed, but sandboxed Windows teardown stalled while stopping its child servers. The two owned test-server process trees on 8001/3001 were stopped after their command/parent identities were checked; the runner then printed its 14-pass summary and exited 0. The live application and user-owned ComfyUI were preserved. Browser regression providers are deliberately mocked; the separate Studio validation above used real Gemini/ComfyUI and the user's local persistence.

A regression guard detected a populated `GEMINI_API_KEY` in `.env.example`. Its old assertion echoed the value in failure output. The example entry was reset to blank while retaining the private `.env` key, and the assertion now operates only on redacted booleans/counts. No key is recorded in this report. The exposed key should be rotated. Production changes are limited to Gemini schema compatibility; the existing ComfyUI/AUTOMATIC1111/generic implementations, job locking, storage and publication architecture were preserved.

Remaining checks: hosted Supabase Auth/Storage; image regeneration and approved publication with real providers (covered with mocks, not exercised live here); precise GPU peak profiling and broader image-quality/continuity evaluation. No further ComfyUI Desktop intervention was needed. See [local SDXL setup](local-sdxl.md), [Phase 3 validation](phase-3-validation.md) and [README](../README.md).

The production frontend was rebuilt and restarted. Frontend **http://127.0.0.1:3000**, backend **http://127.0.0.1:8000** and ComfyUI **http://127.0.0.1:8188** remain running for inspection. Open `/studio/b94ebf4f-0af8-4d4f-8ba1-bde80594d73b` on the frontend to review the saved real panel. Restart FastAPI after rotating/changing the backend key.
