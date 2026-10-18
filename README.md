# StoryVerse · Phase 4 deployment preparation

Public deployment configuration is prepared for **Vercel + Render + Supabase**, with AMD Token Factory text (Gemini fallback) and an authenticated outbound Windows SDXL worker. **No hosted service or public URL has been deployed yet.** Start with the [deployment runbook and environment checklist](docs/deployment.md) and [Phase 4 validation report](docs/phase-4-validation.md). Production refuses the shared demo identity/local persistence; hosted checks await operator account setup.

Collaborative storytelling with **Next.js, TypeScript, Tailwind CSS, FastAPI and Supabase**, optional AMD Token Factory or Gemini text generation and optional local SDXL comic images. Phase 1's UI, data, uploads, profiles, drafts and both reader layouts remain intact.

Phase 3 adds persisted likes, bookmarks, story follows, paginated discovery, private reading progress and richer character continuity. See the [Phase 3 validation report](docs/phase-3-validation.md) and [offline demo walkthrough](docs/demo-guide.md). No live AI credentials or ComfyUI installation are required for these features.

**AI is opt-in.** Without text-provider configuration, the original clearly labeled demo preview works. With a text provider configured, contributors receive structured chapter drafts, dialogue, scenes, summaries and comic-panel descriptions. Local SDXL can render individual panels during review. Nothing is automatically published. Regeneration creates a separate saved version. **Images default off; there are no paid image APIs or automatic model downloads.** See the [updated Phase 2 plan](docs/phase-2-plan.md).

## Run locally

Requires Node.js 20.9+ and Python 3.11+. Dependencies are installed in this workspace. For a fresh checkout, use two terminals:

```powershell
# Terminal 1: from the repository root
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2: from the repository root
cd frontend
npm.cmd ci
Copy-Item .env.example .env.local
npm.cmd run dev
```

Open **http://127.0.0.1:3000**. API documentation: **http://127.0.0.1:8000/docs**. On macOS/Linux use `.venv/bin/python`, `cp` and `npm`. Start services from their indicated directories. When upgrading, preserve your existing `.env` files instead of copying over them.

`APP_MODE=demo` uses persistent SQLite/local files under `backend/data/`, with one shared, labeled demo persona intended for local development. `APP_MODE=supabase` uses real accounts/PostgreSQL/Storage. **`AI_MODE` independently controls generation**; AMD and Gemini can work with either persistence mode.

## Community and reading

Like, bookmark and follow a story from its reading room. The API saves an explicit desired state, so duplicate submissions do not add duplicate actions. Counts come from persisted rows. Your profile includes bookmarked/followed stories and a **Continue reading** library. Individual action rows and reading records are private to the signed-in account; aggregate counts are public. Following keeps a story in your library; it does not send notifications.

Explore supports search, genre filters and 12 stories per page. **Trending** sorts by likes, follows, chapter count, latest publication and a stable ID tie-break. **Recent** sorts by the latest published update, then ID. Bookmarks do not affect ranking. Filters and page numbers stay in the URL. Offset pagination is deterministic for an unchanged dataset; new activity can move results between pages.

Both readers provide previous/next chapter navigation and **Mark chapter read**. Navigation saves the current chapter/layout; marking read records progress through that chapter. Earlier navigation never reduces the completed position. **Continue reading** resumes the saved chapter, or the next chapter after the completed position, using the saved layout. Progress is chapter-based, not scroll/pixel tracking. It is saved to the backend, not browser storage. Anonymous visitors can read/navigate; saving requires an account (or the explicit shared local demo persona).

The published **Story Bible** shows descriptions, relationships, personality traits, visual cues and important events. Character appearance descriptions feed SDXL prompts. New chapter generation preserves established descriptions/visual facts and appends grounded additions; the publication transaction preserves existing canon. Historical chapters are not rewritten. These checks cannot prove semantic consistency in arbitrary prose, so review remains necessary.

## Enable AMD Token Factory (primary)

See the [AMD setup and official API contract](docs/amd-token-factory.md). Configure `AI_MODE=amd`, `AMD_API_KEY`, `AMD_MODEL=DeepSeek-V4-Flash` and `AMD_BASE_URL=https://developer.amd.com.cn/radeon/api/v1` in the private backend environment, then restart. The runtime catalog must mark this exact model free and JSON-capable. Review the provider-specific consent notice before generation. See [actual AMD validation status](docs/amd-validation.md); mocked tests do not establish live inference.

Gemini is an **explicit fallback**: change `AI_MODE` to `gemini` with its existing unpaid-project settings and restart. AMD failures never silently trigger Gemini. Existing provider-neutral generation, canon, versioning, moderation, quota and publication workflows are shared; images are unchanged.

## Enable Gemini (fallback)

1. Create a key in [Google AI Studio](https://aistudio.google.com/apikey) for an **unpaid/free-tier project**. Check that project's tier and billing state in AI Studio. Do not enable billing or use a billed project's key for this zero-cost setup.
2. Set these **backend-only** values in `backend/.env` and restart FastAPI:

   ```dotenv
   AI_MODE=gemini
   GEMINI_API_KEY=YOUR_KEY
   GEMINI_MODEL=gemini-3.5-flash-lite
   GEMINI_FREE_TIER_CONFIRMED=true
   ```

   Keep `backend/.env.example` blank. `Settings` reads `GEMINI_API_KEY` from the backend process environment or `backend/.env`; the default is empty. The example file is documentation, not a place to configure a real key. Automated tests use synthetic fixture values and injected mocks, never this key.

3. Enter a text idea, confirm the data-sharing notice, and choose **Generate with AI**. The unchanged demo action remains separate. Uploaded images/audio/video are preserved but not sent to Gemini.
4. Review and edit the result in Chapter Studio. Generate another chapter version or regenerate one panel description; the previous saved version remains linked and available.
5. Explicitly approve publication. Edited AI prose/title is analyzed before publishing so summary/canon reflect the final saved words. This consumes another quota reservation. If it fails, the chapter stays private.

The official `google-genai` Python SDK uses JSON Schema structured output validated with Pydantic. As checked on **17 October 2026**, Google lists `gemini-3.5-flash-lite` as supported with free-tier standard text input/output. `gemini-3.1-flash-lite` is another verified configurable option. Model availability for your key is checked before the first generation in each worker. See Google's [model catalog](https://ai.google.dev/gemini-api/docs/models) and [pricing](https://ai.google.dev/gemini-api/docs/pricing).

**A key does not expose billing status.** `GEMINI_FREE_TIER_CONFIRMED` is the operator's confirmation, not an automatic billing check. The app cannot prove that your project is unpaid, and it never enables billing. Keep the project unpaid and recheck eligibility before deploying or changing models. No tools, grounding, paid image output, automatic model switching or paid failover is used. Set `AI_MODE=demo` and restart to disable Gemini. Credentials alone do not enable AI or live tests.

Failures and exhausted quotas never become undisclosed demo results. The original contribution remains saved, with a clear error, explicit retry and labeled manual/demo preview.

## Supabase setup or upgrade

1. Apply all five [migrations](supabase/migrations) in order. Existing projects apply only missing migrations: Phase 1 needs **002–005**; Phase 2 needs **004–005**; Phase 3 needs **005 only** (`202610170005_public_deployment.sql`). Do not rerun applied migrations. Use SQL Editor or `supabase link --project-ref YOUR_REF` and `supabase db push` from the repository root. Review the new moderation/storage limits in the [deployment runbook](docs/deployment.md).
2. Enable email/password Auth. Set Site URL `http://127.0.0.1:3000` and allow `http://127.0.0.1:3000/**` redirects; add your production HTTPS URLs when deploying. Confirm signup emails if required.
3. Configure `backend/.env`:

   ```dotenv
   APP_MODE=supabase
   SUPABASE_URL=https://YOUR_PROJECT.supabase.co
   SUPABASE_ANON_KEY=YOUR_PUBLISHABLE_KEY_OR_LEGACY_ANON_JWT
   # Required for AMD, Gemini or SDXL job persistence in Supabase mode:
   SUPABASE_SERVICE_ROLE_KEY=YOUR_SECRET_KEY_OR_LEGACY_SERVICE_ROLE_JWT
   ```

4. Configure matching public credentials in `frontend/.env.local`:

   ```dotenv
   API_INTERNAL_URL=http://127.0.0.1:8000
   NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=YOUR_PUBLISHABLE_KEY_OR_LEGACY_ANON_JWT
   ```

5. Restart both services and sign up/sign in. Local demo records are never copied to Supabase.

Ordinary requests continue to carry the verified **caller JWT**, retaining RLS. Phase 2 uses the backend service identity only for protected AI reservation/result/failure RPCs, which check the owner, draft revision and story version. Browser roles cannot invoke them, fabricate provider payloads, change quota records or rewrite canon. The service role key has broad project privileges: **keep it exclusively on the backend**, never in `NEXT_PUBLIC_*`, browser storage, URLs or source control. Existing demo/manual workflows do not need it. Supabase mode never silently falls back to local storage.

The existing private `story-media` bucket and file validation/ownership policies remain. JPEG, PNG, WebP, GIF, MP3, WAV, OGG, MP4 and WebM are supported, up to 20 MB each and six attachments. Media is public only after publication. Removed unpublished files remain private; automatic orphan cleanup is outside this phase.

## Continuity, privacy and free-tier safeguards

The Context Builder sends the premise, genre/tone, Story Bible, structured earlier summaries, three recent chapters and up to two lexically relevant older excerpts. It bounds the outgoing context instead of sending every chapter body. Earlier manual/sample summaries are labeled extractive; AI summaries describe the final reviewed chapter. Canon tracks characters, relationships, locations, world rules, timeline, events and open/resolved plotlines. Facts append; conflicting existing character/location descriptions are rejected. Human review is still needed for semantic contradictions that structural checks cannot prove.

Only necessary fictional story context, the contributor's idea/direction and, when needed, the reviewed draft go to the selected text provider. Emails, profile metadata, other private drafts and upload contents are excluded. Story text is untrusted contextual data, never system instructions. React renders prose/captions as text. [Google's unpaid-service terms](https://ai.google.dev/gemini-api/terms#unpaid-services) describe product-improvement use and possible human review, with regional qualifications. Do not submit sensitive or confidential personal information; the UI discloses this before AI use.

Defaults, configurable in `backend/.env.example`:

| Safeguard | Default |
| --- | --- |
| Reservations per user / UTC day (text + image jobs) | 10 |
| Shared application reservations / UTC day | 100 |
| User rate / simultaneous jobs | 2 per minute / 1 |
| Global simultaneous jobs | 2 |
| Context payload | 18,000 UTF-8 bytes |
| Input/output tokens | 12,000 / 4,096, Gemini counts instruction/schema allowance; AMD uses a conservative UTF-8 byte preflight budget and reported usage |
| Text provider operation timeout | 45 seconds |
| Gemini temporary 500/502/503 retry | One additional attempt inside that timeout |
| 429 / timeout retry | Explicit user action; no automatic retry |

Failed attempts count conservatively toward quotas. Reservations, results and leases persist across restarts. SQLite transactions and PostgreSQL locks protect concurrent workers. Repeated request IDs reuse a completed result or report its existing state; explicit new attempts use new IDs. Interrupted leases release concurrency slots after expiry. Logs include job/model/token/status metadata, never prompts, private prose, secrets or raw SDK errors.

## Comic panels

The selected text provider produces 2–4 descriptions with characters, location, camera and caption. With SDXL disabled or offline, Studio and both readers retain clearly labeled **“Placeholder · Panel description · No image generated”** panels and uploaded media. Text preview/edit/regeneration, approval and publication still work.

To connect local SDXL, install a separate [AUTOMATIC1111 runtime](https://github.com/AUTOMATIC1111/stable-diffusion-webui#installation-and-running), select an SDXL checkpoint, and enable its API on loopback. On Windows, its `webui-user.bat` can use `set COMMANDLINE_ARGS=--api --medvram-sdxl`; follow its own Python/GPU installation requirements. StoryVerse does not install PyTorch or weights. See the runtime's [API](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API) and [memory options](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/Command-Line-Arguments-and-Settings).

Set these backend values and restart FastAPI:

```dotenv
SDXL_ENABLED=true
SDXL_API_FLAVOR=a1111
SDXL_BASE_URL=http://127.0.0.1:7860
SDXL_MODEL=sd_xl_base_1.0.safetensors
SDXL_WIDTH=768
SDXL_HEIGHT=768
SDXL_STEPS=20
SDXL_TIMEOUT_SECONDS=120
```

These are conservative starting settings for an RTX 4050, **not measured compatibility or performance guarantees**. Batch/count stay fixed at one, without a refiner or high-resolution pass. Low-VRAM/offload behavior belongs to the runtime. Runtime and backend must share a loopback network namespace. Alternative local inference services can use the documented `generic` endpoint contract.

**ComfyUI is also supported natively.** Install it separately, place your SDXL base checkpoint in `models/checkpoints/`, and start its loopback server with memory offloading (for a manual install: `python main.py --listen 127.0.0.1 --port 8188 --lowvram --preview-method none`). Configure the same SDXL size/step defaults above plus:

```dotenv
SDXL_API_FLAVOR=comfyui
SDXL_BASE_URL=http://127.0.0.1:8188
COMFYUI_SAMPLER=dpmpp_2m
COMFYUI_SCHEDULER=karras
COMFYUI_POLL_INTERVAL_SECONDS=1
```

The adapter submits a built-in base-only workflow, polls execution history and downloads one PNG through ComfyUI's native API. It uses tiled VAE decoding; no custom nodes or workflow export is required. The existing AUTOMATIC1111 and generic adapters remain available. See [ComfyUI setup](docs/local-sdxl.md#comfyui-native-api), including runtime/version memory options and temporary-file privacy. **Real Gemini → Studio → ComfyUI SDXL generation and private versioned storage were verified on the local RTX 4050.** The opt-in SDXL test took 20.17 seconds; Studio's panel action took 20.29 seconds, with no OOM and a maximum sampled GPU usage of 5,513/6,141 MiB. See the [live validation report](docs/live-comfyui-validation.md) for evidence and remaining quality/hosted-storage checks.

Generate text first, then choose **Generate image** on a panel in Studio. Regenerate one image without calling Gemini; previous versions and manual attachments remain available. Prompts combine the chapter's panel description with fictional character appearance notes. Images go through the existing private upload/storage flow, with model, seed, dimensions and generation metadata. Only the approved version's images become public, atomically with its chapter. Description regeneration removes its outdated image from the new version while preserving the previous version.

The [complete live Studio validation](docs/live-studio-validation.md) verifies real Gemini panel descriptions, SDXL generation/regeneration, saved files across backend restarts, edited-chapter analysis, approval/publication and both responsive readers on a dedicated local validation story. Hosted Supabase remains a separate live check; artwork still needs review for prompt fidelity.

The backend allows one active image job across users/workers and checks runtime busy state. Image requests have bounded sizes/timeouts and **no automatic retries**. After a timeout, the GPU may still be rendering: wait until idle before retrying. Failures preserve descriptions and previous images. No remote image URL is fetched, no cloud image provider is selected, and no paid fallback exists.

Full setup for all three adapters, endpoint schemas and troubleshooting: [local SDXL guide](docs/local-sdxl.md). Verified local inference and remaining Studio/hosted-service limits: [live validation](docs/live-comfyui-validation.md).

## Tests and build

```powershell
# From backend/
.\.venv\Scripts\python.exe -m pytest -q

# From frontend/
npm.cmd run typecheck
npm.cmd run test:db
npm.cmd test
npm.cmd run build
npm.cmd start
```

Original Phase 1/2 tests remain. Gemini SDK calls and SDXL/ComfyUI HTTP calls are mocked; image workflow fixtures return an explicitly labeled flat-color test PNG. Phase 3 tests cover persisted actions, concurrency/idempotence, library privacy, progress, discovery and visual continuity. Configuration tests verify backend environment loading, secret exclusion from settings representations, a blank example template, and safe missing-key behavior without constructing an SDK client. PostgreSQL/PGlite executes all four migrations with stand-ins for Supabase's Auth/Storage schemas, checking RLS/grants and publication/continuity contracts. It does not run hosted Supabase services.

Playwright starts isolated servers on **8001/3001**, with disposable records and **clearly labeled mocked Gemini/SDXL providers**. Eighteen journeys cover community/library persistence, reading resume, discovery pagination, Phase 1, text generation, offline image fallback, image regeneration, queued remote results/recovery, moderation controls and both readers at 1440px and 390px. Its 18 additional old-dated discovery fixtures exist only in the disposable test database. The browser fixture relaxes the shared persona's minute cap; dedicated API/SQL tests verify production quotas. Windows uses installed Edge; elsewhere run `npx playwright install chromium`. `PLAYWRIGHT_CHANNEL` overrides the channel. Screenshots/traces are in `frontend/test-results/`.

**Optional live Gemini test:** set `STORYVERSE_LIVE_GEMINI_TESTS=1`, `AI_MODE=gemini`, `GEMINI_API_KEY` and `GEMINI_FREE_TIER_CONFIRMED=true` for an unpaid project. Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gemini_live.py -q
```

This makes a real generation operation with bounded retries. Credentials alone never enable it. **The live Gemini test and actual Studio chapter generation passed on 17 October 2026** after the operator configured an unpaid-project key. The live schema compatibility fix retains strict local validation; see [the live report](docs/live-comfyui-validation.md). Prose quality and semantic continuity still need human review.

**Optional live Supabase test:** use a disposable migrated project with two confirmed accounts. Set `STORYVERSE_LIVE_TESTS=1`, `SUPABASE_TEST_EMAIL_A`, `SUPABASE_TEST_PASSWORD_A`, `SUPABASE_TEST_EMAIL_B`, `SUPABASE_TEST_PASSWORD_B` plus project settings. Run `tests/test_supabase_live.py` through virtualenv pytest. It creates permanent `[Integration test]` records and is skipped by default. No hosted Supabase credentials were supplied here.

**Optional live SDXL test:** start your local runtime, configure `SDXL_ENABLED=true` and explicitly set `STORYVERSE_LIVE_SDXL_TESTS=1`, then run `tests/test_sdxl_live.py` through virtualenv pytest. This performs one actual local render, independently of Gemini. See the [guide](docs/local-sdxl.md#live-verification).

See the current [Phase 3 validation report](docs/phase-3-validation.md), [Phase 2 report](docs/phase-2-validation.md), [SDXL/ComfyUI validation](docs/sdxl-validation.md), [architecture/API reference](docs/architecture.md), and historical [Phase 1 report](docs/validation.md).

## Deployment and source

`backend/app/ai/` contains text/image provider adapters, schemas, context, services and persistence helpers. `backend/app/community.py` adds repository helpers for engagement, discovery and reading progress. Existing frontend components gained reusable community/reader controls, without a redesign. Migrations 2–4 are additive and preserve published prose.

Host Next.js on a Node-compatible provider and FastAPI on a Python-compatible provider. Set server-only `API_INTERNAL_URL` to the API origin; the browser uses the existing same-origin `/api` proxy. Supply public Supabase variables at frontend build time. Configure HTTPS, redirects and CORS for deployment. No site, native app or APK has been deployed.
