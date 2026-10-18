# StoryVerse local demo and troubleshooting

Use the existing two-terminal [README setup](../README.md#run-locally). Keep `APP_MODE=demo`, `AI_MODE=demo` and `SDXL_ENABLED=false` in the backend environment for a fully offline walkthrough. Frontend: `http://127.0.0.1:3000`; FastAPI health/docs: `http://127.0.0.1:8000/api/health` and `/docs`. No model runtime, API key or Supabase project is needed. Existing `.env` files should be preserved, not overwritten.

The local demo uses real SQLite/files under `backend/data/` and one shared **Demo profile**. It is intended for local presentations, not public multi-user hosting. Supabase mode provides separate authenticated accounts when configured. No local record is silently copied to Supabase.

## A five-minute walkthrough

1. Open **The Forest That Remembers**, the hand-written three-chapter sample. Follow Elara's mother's brass key through the fox's house to the stopped river. Open **Story Bible** to show the persistent character/appearance notes and important events. The cover is sample artwork, not a generated comic panel.
2. Like, bookmark and follow it. Refresh to demonstrate persistence. Open **My stories** → **Bookmarked** and **Followed**. Return to the reading room; pressing a selected action removes it without duplicate-count errors.
3. Switch between **Webtoon** and **Comic book**. Use **Next**, mark a chapter read, then visit **My stories** → **Continue reading**. Resume the next unread chapter with the saved layout. These are stored chapter cursors, not browser-only scroll positions.
4. Choose **Continue story**. Enter a short continuation, for example: “The jar held one word in her mother's voice: remember. The fox arrived carrying a second, broken key.” Choose **Generate preview**. This action copies your words unchanged and is clearly labeled; it does not call AI.
5. Edit the chapter title and prose, save, refresh, and preview. Choose **Approve & publish**, then confirm **Publish chapter**. The new chapter appears publicly in both readers and updates **Recent**. Published chapters are permanent. Use a new story if you want to leave the sample's three original chapters as the whole presentation.
6. Explore **Trending**, **Recent**, genre filters and search. Pagination appears for larger collections. User engagement drives ranking; no fake likes, followers or generated stories are prefilled.

For a repeatable clean presentation without deleting existing data, point `DATA_DIR` to a new directory such as `data/demo-session-2` and restart FastAPI. This creates a separate database with the same six curated samples. Restarting against the same directory preserves edits, publications, actions and progress.

## Optional AI demonstration

Live Gemini and SDXL/ComfyUI remain unverified. They are independent opt-ins. Only enable Gemini with your backend key and unpaid-project confirmation; configure local SDXL as described in the [image guide](local-sdxl.md). Defaults remain 768×768, 20 steps, one panel at a time, no refiner. Downloads can continue independently of the offline demo.

With configured providers: **generate text → review/edit/regenerate → optionally generate panel images → approve → publish**. Edited AI chapters may need final-text analysis before publication. An unavailable provider preserves the saved draft and descriptions; it never becomes an undisclosed mock success. Automated browser tests use visibly marked fixtures; those labels must not be presented as live model results.

## Troubleshooting

| Symptom | Check/action |
| --- | --- |
| “Couldn't reach StoryVerse” | Run FastAPI from `backend/`; check `/api/health`, then `API_INTERNAL_URL` in `frontend/.env.local`. Restart Next.js after changing it. |
| PowerShell blocks `npm.ps1` | Use the documented `npm.cmd` commands. |
| Profiles, actions or discovery fail in Supabase mode | Apply all missing migrations through `202610170004_community_reading.sql`; restart API. No silent local fallback exists. |
| Sign-in/session error | Verify matching backend/frontend Supabase project credentials, email confirmation and allowed redirect URLs. Community writes use the caller JWT, not the AI service key. |
| An action count seems stale in another tab | Refresh that tab. Counts are computed from persisted rows; the UI is not a realtime subscription. Repeated desired-state requests remain idempotent. |
| Reading place did not save | Check the visible error and API connection. Use chapter navigation or **Mark chapter read** while signed in; scrolling alone does not write progress. |
| Empty discovery page after new activity | Return to the previous page or reset filters. Ranking can change between offset-paginated requests. |
| Story version conflict at publish | Another chapter won. Keep a copy of your prose, read the latest story and begin a new contribution. Existing drafts cannot overwrite the new version. |
| Gemini actions disabled | `AI_MODE=gemini`, backend `GEMINI_API_KEY` and unpaid confirmation are required. The offline demo action remains usable. |
| SDXL offline, busy or timed out | Keep descriptions/previous images. Start the selected local runtime and wait until idle before explicitly retrying. A timed-out render may continue externally. |
| ComfyUI rejects the workflow | Check the exact installed SDXL checkpoint name, native sampler/scheduler and built-in nodes in its local console. See the image guide. |

Automated checks: backend `python -m pytest -q`; frontend `npm.cmd run test:db`, `npm.cmd test`, `npm.cmd run typecheck`, `npm.cmd run build`. Playwright uses isolated servers on 8001/3001, disposable data and mocked providers. See the [Phase 3 validation report](phase-3-validation.md) for tested versus unverified integrations.
