# Phase 2 local SDXL extension validation

Historical Phase 2 results are retained here. Community/reading validation is in the [Phase 3 report](phase-3-validation.md). Subsequent **real Gemini and ComfyUI SDXL inference, Studio and private-storage validation** is recorded in the [live report](live-comfyui-validation.md); hosted Supabase remains unverified.

Date: **17 October 2026**, Windows, Python 3.13.5, Node.js 24.20.0, Next.js 16.4.2, Pillow 12.3.0, installed Microsoft Edge via Playwright. Updated for native ComfyUI support; backend results were rerun for this extension. Frontend/database rows below retain the previous SDXL run's results because those implementations were unchanged.

## Implemented

Gemini remains the backend text provider and reads `GEMINI_API_KEY` from the backend environment. No credential is hardcoded or added to the example template. The optional local image adapter supports AUTOMATIC1111, native ComfyUI and a documented generic SDXL HTTP contract. No GPU libraries, weights or paid image APIs were added. The initial SDXL extension added only Pillow for bounded PNG validation; ComfyUI support adds no dependencies.

Native ComfyUI uses built-in nodes for a single base-model workflow, with tiled VAE decoding and a temporary PNG output. It checks `/queue`, submits `/prompt`, polls `/history/{prompt_id}` and retrieves validated local image references through `/view`. Sampler/scheduler and polling interval are configurable. The existing local provider retains the overall timeout, HTTP/image bounds and loopback restriction; `PanelImageService` retains durable locking, ownership, draft versions, uploads and approval/publication. No frontend feature or migration was changed for ComfyUI.

SDXL defaults off. Configured requests render one panel at a time, initially 768×768/20 steps with no refiner or high-resolution pass. Runtime memory/offload settings are documented separately. A shared durable reservation protects a single local image job across users/workers. Timeouts and response sizes are bounded; image calls never automatically retry or switch providers.

Studio supports individual image generation/regeneration after text generation. Each success creates a new private draft version. Existing text, other panels, manual uploads and previous versions remain intact. Description regeneration retires its outdated image only in the new version. Missing/offline SDXL retains labeled descriptions and previous images; it never fabricates generated artwork.

Generated files use the existing local/Supabase upload flow and store panel model, dimensions, seed, settings, hashes and provenance. An additive third migration validates ownership and publishes referenced image files/panel rows atomically with the version-checked chapter. Images appear once in each reading layout. Explicit approval remains mandatory.

## Executed checks

| Check | Result without live credentials/runtime |
| --- | --- |
| Backend dependency installation and lock snapshot | Passed; Pillow installed, no GPU packages or weights |
| `python -m pytest -q` | **78 passed, 3 skipped**, live opt-in flags explicitly disabled; all HTTP/model calls mocked |
| New native ComfyUI tests | **28 passed** within the full backend suite; no ComfyUI runtime required |
| `npm.cmd run test:db` | Previous SDXL run: passed; all three actual migrations executed in PostgreSQL/PGlite; SQL unchanged for ComfyUI |
| `npm.cmd test` | Previous SDXL run: **10 passed**, including original six Phase 1 journeys and four extended AI journeys at desktop/mobile widths; frontend unchanged |
| `npm.cmd run typecheck` | Previous SDXL run: passed; frontend unchanged |
| `npm.cmd run build` | Previous SDXL run: passed; all routes built; frontend unchanged |
| Running frontend/backend | Previous SDXL run: Playwright launched isolated Next.js and FastAPI processes and verified the API proxy through actual browser interactions. This extension also exercises FastAPI through TestClient. |
| Local SDXL discovery | Original SDXL inspection found no listeners on loopback ports 7860, 8188 or 8002. No live ComfyUI inference was attempted for this extension. |

Backend SDXL coverage comprises 18 tests: mocked AUTOMATIC1111/generic HTTP contracts; conservative request settings; remote/credentialed/malformed endpoint rejection; unavailable/busy/mismatched/invalid/timed-out responses; disabled-image fallback; private uploads; replay/idempotence; new versions and regeneration seeds; selected-image publication while older files stay private; no-Gemini-key operation; ownership; concurrent image exclusion; in-flight edit rejection; and description regeneration preserving other panel images. The preceding 32 Gemini/configuration/Phase 1 tests remain passing.

The 28 additional ComfyUI tests cover the native workflow/submission/history/view protocol, environment loading, 768×768/batch-one/20-step defaults, one base checkpoint/sampler, tiled decoding, busy or invalid queues, rejected submissions, unsafe execution IDs, execution/interruption errors, incomplete output, missing/multiple images, unsafe file references, redirect rejection, invalid/missing/oversized PNGs, total polling timeout without resubmission, private uploads, replay, individual regeneration, preserved descriptions/images after failure, publication, image-job exclusion during polling and in-flight edits rejecting stale results. Existing AUTOMATIC1111 and generic tests pass in the same suite.

PostgreSQL tests execute migrations with synthetic Supabase Auth/Storage schemas. They check the original policies/publication rules plus service-only image jobs, denied access to unwrapped base functions, single-image exclusion across two users, rejection of another user's image, owner-private files before publication, public files afterward and persisted panel metadata. They do **not** exercise hosted Supabase network/Auth/Storage services.

Browser journeys use injected Gemini and SDXL fixtures, with a flat-color PNG visibly labeled **“Mocked SDXL test image · No local inference.”** They test unavailable-image fallback, explicit retry, image regeneration/new-version links, private preview loading, final text edits, approval, publication and both readers. Loaded image dimensions and duplicate rendering are checked, as is viewport overflow at 1440px and 390px. The fixture server relaxes its shared demo persona's minute quota; separate API/database tests check production quotas.

Screenshots from the passing run: [desktop Studio](screenshots/phase-2-sdxl-studio-desktop.png), [mobile Studio](screenshots/phase-2-sdxl-studio-mobile.png). The flat-color image is a test fixture, not generated artwork.

The first browser run failed on an ambiguous `role="alert"` selector matching Next.js's route announcer. The selector was corrected; the complete rerun passed. The existing upstream Starlette/httpx deprecation and Node color-environment warnings are non-fatal.

## Live integration status

| Integration | Status and remaining requirement |
| --- | --- |
| Gemini | **Not verified live.** Provide a backend key for an unpaid project, confirm the tier, and opt into `tests/test_gemini_live.py` with `STORYVERSE_LIVE_GEMINI_TESTS=1`. Real account/model availability and writing quality remain unverified. |
| Local SDXL (including ComfyUI) | **Not verified live.** Install/start a compatible local runtime and checkpoint, configure backend variables, then opt into `tests/test_sdxl_live.py` with `STORYVERSE_LIVE_SDXL_TESTS=1`. For ComfyUI use `SDXL_API_FLAVOR=comfyui`. Actual GPU inference, RTX 4050/6 GB compatibility, peak VRAM, latency and quality remain unverified. |
| Hosted Supabase | **Not verified live.** Apply migrations to a disposable project and configure the documented two test accounts, then run `tests/test_supabase_live.py` with `STORYVERSE_LIVE_TESTS=1`. |

Credentials alone never activate live tests. `/api/health` reports configuration and `runtime_status: "not_verified"`; enabling SDXL is not proof that inference works. The live SDXL test validates a real returned PNG; full Studio-to-Storage operation should then be checked against the user's configured services.

## Persistence and limits

Local SQLite, private files, saved draft versions and publication are real persistence, exercised with mocked model results. PostgreSQL policies/functions are implemented and SQL-tested; the hosted Supabase connection is conditional on user configuration. Fixture generation is test-only; production has no automatic mock fallback. Offline image fallback consists of the saved descriptions/placeholders, not a fake AI image.

A timeout cannot guarantee that an external GPU stopped: wait for idle before retrying. An unrelated runtime client can race a busy probe, so the runtime must also serialize its work. A file saved before a subsequent stale-result rejection remains private and may become an orphan; cleanup is not included. No background queue, model downloading, paid provider, native application or APK was introduced.

See [updated plan](phase-2-plan.md), [local SDXL setup and endpoint contract](local-sdxl.md), [README](../README.md) and [architecture](architecture.md).
