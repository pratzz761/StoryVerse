# Validation · 17 October 2026

Historical **Phase 1** results are retained below. See [Phase 3 validation](phase-3-validation.md) for current results, or [Phase 2](phase-2-validation.md) and [SDXL/ComfyUI](sdxl-validation.md) for earlier implementation details.

Verified locally on Windows with Node.js 24.20.0, Python 3.13.5, and Microsoft Edge through Playwright.

| Check | Result |
| --- | --- |
| Frontend dependency installation | Passed; `package-lock.json` included |
| Backend dependency installation | Passed in `backend/.venv`; verified pins in `requirements.lock.txt` |
| Next.js production build | Passed; all application routes built |
| TypeScript `tsc --noEmit` | Passed |
| FastAPI tests | **9 passed** |
| Live Supabase integration test | **1 skipped**; project credentials not supplied |
| Actual migration in PostgreSQL/PGlite | Passed, including grants, RLS, ownership, approval, storage visibility and publication conflicts |
| Playwright browser journeys | **6 passed** across desktop 1440 × 1000 and mobile 390 × 844 |
| Frontend and API runtime | Both started successfully; frontend returned HTTP 200 and proxied API health correctly |
| Production responsive smoke check | Feed/create pages passed at 390, 768, 1024 and 1440px; screenshots included under `docs/screenshots/` |

Browser journeys cover Explore filters and search, both reader modes and pagination, creating a story with an uploaded PNG, continuing a story, editing and saving a draft, persistence after refresh, previewing, explicit publish confirmation, public chapter display, created/contributed profile lists, profile updates, unpublished draft recovery, and honest demo regeneration. They check for page-width overflow and uncaught browser errors in the reading journey. Screenshots of the feed, reader and studio are produced in `frontend/test-results/`.

The API suite verifies durable records after restart, input and file validation, audio storage, file-size limits, cross-owner upload and draft restrictions, preview reset, explicit approval, and two simultaneous publish requests producing one success and one 409 without data loss. The Supabase adapter is tested with a mocked HTTP transport to verify token validation/forwarding and conflict mapping. The database suite executes the actual migration and policy checks, with substitute `auth` and `storage` schemas.

These tests do not substitute for a hosted Supabase round trip. Follow README's opt-in live test to verify real Auth, PostgREST and Storage with two confirmed accounts in a disposable project. One upstream Starlette deprecation warning is emitted by the current FastAPI TestClient/httpx integration; all API assertions pass.

All AI-related UI is explicitly demo-only. No model API, generation engine, mobile app, APK, or hosted deployment was created. User text, files, drafts, profiles and chapter publication use real local persistence in demo mode and the Supabase adapter when configured.
