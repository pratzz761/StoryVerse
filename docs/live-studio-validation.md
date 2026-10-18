# Complete live Studio validation

Date: **17 October 2026**. Follow-up to [initial live ComfyUI validation](live-comfyui-validation.md), using the operator's current backend environment. No API key, credential fingerprint, raw SDK response error, or request header is included in this report.

## Configuration and scope

- FastAPI: `http://127.0.0.1:8000`; production frontend: `http://127.0.0.1:3000`.
- `AI_MODE=gemini`, `GEMINI_FREE_TIER_CONFIRMED=true`, model `gemini-3.5-flash-lite`. The operator previously explicitly confirmed an unpaid/free-tier project. The key is loaded from the backend environment/ignored `backend/.env`; `.env.example` remains blank.
- `SDXL_ENABLED=true`, `SDXL_API_FLAVOR=comfyui`, endpoint **http://127.0.0.1:8188**, checkpoint **sd_xl_base_1.0.safetensors**.
- **768×768, 20 steps, batch one, CFG 6, dpmpp_2m/karras, tiled VAE, no refiner**, 300-second timeout. Existing ComfyUI installation/checkpoint were reused without downloads or reinstalls.
- `APP_MODE=demo`: durable SQLite and local files under `backend/data/`, using the explicit shared local demo persona. **Text and images were real provider results**, not demo generation, injected fixtures or mocked HTTP. Hosted Supabase was not configured or verified.

FastAPI was restarted before validation so it used the current environment/key. The live flow created its own story, **Live validation: The Last Lantern**, rather than publishing into an existing story. All 25 pre-existing stories, chapters, drafts, upload metadata and Story Bible rows retained their original hashes.

## Fresh test results

| Check | Actual result |
| --- | --- |
| Existing opt-in Gemini integration test | **Passed**, 6.78 seconds |
| Existing opt-in SDXL integration test | **Passed**, 17.74 seconds |
| Combined live test command | **2 passed in 25.07s**, exit 0 |
| Default backend regression suite | **95 passed, 3 skipped in 11.70s**, exit 0 |
| Fresh complete Studio journey | **Passed**, real generation, edit/preview, image regeneration, review analysis, approval/publication |
| Published readers | **Passed**, Webtoon and Comic Book at 1440px desktop and 390px mobile |
| Storage across backend restarts | **Passed**, private versions and published output retrieved after restart, matching hashes |
| Publication replay / stale draft | **Passed**, replay HTTP 200 without duplication; stale version correctly rejected with HTTP 409 |

Live tests ran explicitly from `backend/`:

```powershell
$env:STORYVERSE_LIVE_GEMINI_TESTS="1"
$env:STORYVERSE_LIVE_SDXL_TESTS="1"
.\.venv\Scripts\python.exe -m pytest tests/test_gemini_live.py tests/test_sdxl_live.py -q --durations=2 --tb=no -p no:cacheprovider
```

The separate backend regression invocation explicitly disabled live opt-ins. Its three skips are the opt-in Gemini, SDXL and hosted Supabase tests. Provider calls in that default suite are mocked; they are distinct from the actual live tests/journey above. One existing Starlette/httpx deprecation warning was emitted. No production code or dependencies changed in this follow-up, so the prior production build, TypeScript, 14 browser regressions and migration results remain historical results in the [earlier report](live-comfyui-validation.md), not fresh reruns claimed here.

## Studio actions and saved versions

Story: `3bf4eb98-85e5-4118-b469-97df698ce915`.

1. Created a hand-written opening through **Create story**, then entered a contributor idea and approved the Gemini disclosure through **Continue story → Generate with AI**. HTTP 200 in **6.776 seconds**. Real chapter draft: `700cff58-a221-4363-9c3b-ba695cca88bb`, with **two panel descriptions**, narrative, summary and structured memory. Saved metadata records `provider: gemini`, `is_test_fixture: false`, 679 input and 998 output tokens. No fixture or imported diagnostic chapter was used.
2. Used **Generate panel 1 image → Generate image locally**. HTTP 200 in **17.361 seconds**. New private draft: `91290cf8-3969-4093-9a50-b62b1bf5c696`; previous text draft and unselected panel stayed intact.
3. Used **Regenerate panel 1 image**. HTTP 200 in **16.325 seconds**. New private draft: `49542e23-d448-484e-bd8d-788eaad5e3b3`; seed incremented **42 → 43**, image bytes/hash changed, and the previous image/draft, reviewed text and other panel were preserved. This action used ComfyUI without another Gemini call.
4. Restarted FastAPI and retrieved both drafts and image files through the real API. Both on-disk and downloaded hashes still matched.
5. Edited the final title to **The Lantern and the Hidden Mark**, appended a sentence, clicked **Save draft**, and checked the **Preview** tab. Used **Approve & publish → Publish chapter**. HTTP 200 in **4.979 seconds**, including a real Gemini analysis of the edited words. Its durable memory job records 769 input and 393 output tokens; the stored memory hash matches the final title/narrative.
6. Verified story version **2**, two published chapters and Story Bible version **2**. The final image appears in both readers on desktop/mobile, without horizontal overflow. Replayed publication returned the same result without a duplicate chapter. Publishing the older image draft returned the expected **409 conflict**. Repeated these reader/replay checks successfully after another backend restart.

Published chapter: `d76d27d7-dcfe-4fd2-b6f0-9f7895f8f8ad`. [Open the local validation story](http://127.0.0.1:3000/stories/3bf4eb98-85e5-4118-b469-97df698ce915).

## Real PNGs and storage

| Property | First generation | Regenerated / approved version |
| --- | --- | --- |
| ComfyUI execution ID | `c7f15e84-8d5f-47f5-820b-a53edbd9b884` | `cb469b56-783e-46f4-ab45-ef9da5f8783d` |
| Upload ID | `4b23c638-b1c9-416d-84c6-dfdcab885818` | `87163857-ed80-4aaa-a329-5ea2abf63028` |
| PNG dimensions | 768×768 | 768×768 |
| Bytes | 1,063,189 | 922,211 |
| Seed | 42 | 43 |
| Visibility after publication | Private, previous version | Public, referenced approved version |

First image SHA-256: `55845c901a91320882c2bc8c8553383f3878cdc9b7200d0390c745f69f059fd9`.

Approved image SHA-256: `0fb1bf4f303e2a7095f72fdd7f4989ba8f5ea0c1332fd1e9c92aaa22b425785c`.

Both images passed the existing PNG validation/storage path and match the saved metadata, local files (`backend/data/uploads/{upload_id}`) and frontend-proxied API downloads. Metadata includes model, dimensions, sampler/scheduler, steps, seed, prompt hash, native execution ID and `is_test_fixture: false`. ComfyUI history reports success for both executions. No OOM or execution error occurred; GPU peak usage was not profiled during this follow-up.

Before approval, actual local repository reads using another owner were denied for the private draft and image (404). After approval, the selected image is public and accessible to another caller; the replaced image remains private and its foreign-owner read is denied. These are real local repository/SQLite checks, not hosted Supabase authentication or RLS verification. The demo HTTP mode deliberately shares one persona.

Ignored local evidence is under `backend/data/live-validation/`:

- `complete-studio-result.json`: timed UI results, version IDs and image metadata.
- `complete-private-storage.json`, `complete-restart-storage.json`, `complete-storage-publication.json`: ownership, persistence, memory/publication and checksum evidence.
- `complete-existing-records.json`: hashes of the 25 pre-existing records.
- `complete-first-panel.png`, `complete-regenerated-panel.png` and `complete-*.png` screenshots of Studio and both responsive readers.
- `complete-studio.mjs`: opt-in staged real browser validation script. It performs live generation/publication on its own validation story, never runs in the default test suite, and refuses to repeat already completed generation stages.

## Failures, limits and remaining checks

**No live generation or publication action failed in this follow-up.** The stale-publication 409 was an expected successful safety check. Provider schema compatibility introduced during the earlier validation remains in place; no new implementation fix was needed.

Visual review found prompt-fidelity limitations: the regenerated image depicts the copper-haired character but uses a light coat and yellow/orange flame rather than the requested navy coat and blue flame. Actual inference/storage is verified; perfect character/color consistency is not. The second panel remains a clearly labeled description-only placeholder. Only the explicitly approved image version was published on this local validation story.

The shared demo persona has now consumed **10/10 application generation reservations** for 17 October UTC, including earlier attempts. All four new workflow jobs (`chapter`, `image`, `image`, `memory`) succeeded. Quotas were not raised or bypassed, and no Google quota error was observed. Further new generations under the unchanged daily cap wait until **18 October 2026 00:00 UTC / 05:30 IST**. Reading, saved files and replaying an already completed publication remain available. The configured daily limit is `AI_USER_DAILY_LIMIT` in the backend environment.

Hosted Supabase Auth/Storage/RLS still requires separate live credentials/testing. The follow-up did not verify paid services, other image adapters against real runtimes, multi-user hosted concurrency, or semantic/visual consistency across many chapters. Current credentials were checked in memory against reports, examples and validation JSON/scripts; the scan was clean and no credential values were logged.

The frontend, backend and user-owned ComfyUI remain running at the endpoints above. Existing stories/drafts were preserved; the newly created local validation story remains available for inspection.
