# Phase 3 implementation and validation

Subsequent **real Gemini → Studio → ComfyUI SDXL generation**, private storage, sampled VRAM and updated regression results are recorded in the [live validation report](live-comfyui-validation.md). The original Phase 3 test results and integration status below are retained as historical evidence.

The [complete live Studio follow-up](live-studio-validation.md) additionally verifies actual image regeneration, edited-chapter analysis, approved publication, restart persistence and desktop/mobile public readers using local SQLite/files. Hosted Supabase remains unverified.

Date: **17 October 2026**. Windows, Python 3.13.5, Node.js 24.20.0, Next.js 16.4.2, PostgreSQL/PGlite and Microsoft Edge through Playwright. Work extended the existing repository and visual design. No model runtime, paid service, extra dependency, deployment or native app was added.

## Implemented features

| Area | Behavior and persistence |
| --- | --- |
| Community | Likes, bookmarks and story follows persist as one row per user/story/action. Setting the same desired state repeatedly is safe. Counts are computed from stored rows. Selected controls can remove an action; buttons wait for the server result. |
| Profiles | Created/contributed lists remain; bookmarked, followed and continue-reading libraries are added. Action rows and progress belong to the authenticated reader. Followed stories reflect their latest published update; notifications are not included. |
| Discovery | Public search, genre filters and pagination with total/page/next metadata. Trending uses likes, follows, chapter count, latest update and stable ID. Recent uses latest publication/update and stable ID. Ranking uses no invented counts, random scores or external service. Filters/page survive refresh in the URL. |
| Readers | Both layouts retain their media, prose and contributor credits. Previous/next and chapter-index navigation save the current chapter/layout. Mark-read persists progress through a chapter. Resume opens the saved or next unread chapter, including from Profile. Responsive images, themed progress, loading/error and empty states are included. |
| Character consistency | Characters retain descriptions, relationships, personality traits and optional visual descriptions. New traits/relationships/events append; established descriptions/visual facts cannot be replaced. Empty visual facts may be enriched once. Visual descriptions feed SDXL prompts. Published Bible facts appear in the reading room. |
| Samples/demo | The original six hand-written samples remain, including the three-chapter Forest story. Curated character/event notes enrich that sample's previously empty Bible without changing its chapters or existing user/AI canon. Offline contributor → preview/edit → explicit approval → publication remains usable. |
| ComfyUI | The existing native adapter is preserved: queue check, workflow submission, history polling, PNG retrieval; 768×768, 20 steps, batch one, no refiner, tiled VAE. AUTOMATIC1111 and generic adapters remain. All 28 native ComfyUI tests run without a server. |

## Database, authorization and version safety

New additive migration: [202610170004_community_reading.sql](../supabase/migrations/202610170004_community_reading.sql). Apply it after migrations 001–003. Earlier chapters/narrative are not backfilled or rewritten.

- `story_interactions`: composite primary key, owner-scoped RLS and caller-JWT writes. Public aggregate functions return counts and only the caller's own flags, never other readers' individual actions. Anonymous writes and cross-user rows are rejected.
- `reading_progress`: private user/story cursor, chapter/story foreign-key relationship and guarded write RPC deriving identity from `auth.uid()`. Direct browser writes are denied. Duplicate writes preserve the existing row; moving backward never decreases the completed position.
- `discover_stories`: bounded, literal substring filtering and explicit deterministic aggregate ordering, with matching count/page metadata from one database operation. Legacy `/api/stories` array clients remain supported.
- Character fields remain backward-compatible JSON. The existing chapter-memory trigger permits filling an unknown empty visual description while preserving containment of established canon. A later conflicting appearance is rejected transactionally.
- Existing draft ownership, expected story versions, revision checks, image reservations, private uploads, final-text memory analysis and atomic publication remain intact. Community actions do not need the AI service-role key. Browser and ordinary storage requests keep caller JWTs; keys stay server-side.

Local demo mode implements the same community/progress contracts in actual SQLite transactions and files, using the explicitly shared demo persona. Supabase mode has the implemented tables, RPCs and policies; hosted service validation remains pending.

## Checks executed

| Check | Result |
| --- | --- |
| Backend `python -m pytest -q` | **90 passed, 3 skipped**. Live Gemini, SDXL and Supabase flags explicitly disabled. |
| New Phase 3 backend tests | **12 passed** within that suite: concurrent duplicate actions/removal, restart persistence, private libraries/progress, chapter validation, deterministic pagination/ranking, auth/caller-JWT routing and visual/canon protection. |
| Native ComfyUI tests | **28 passed**, including workflow/polling/view, failure paths, image bounds, locking, versioning and publication. These are mocked HTTP tests, not GPU inference. |
| `npm.cmd run test:db` | **Passed.** All four actual migrations executed in PostgreSQL/PGlite with stand-ins for Supabase-owned Auth/Storage schemas. |
| `npm.cmd test` | **14 passed**: seven journeys at desktop 1440px and mobile 390px. Original Phase 1/2 journeys retained; four new runs cover community, profiles, reading and discovery. |
| Final focused community browser rerun | **4 passed**, exercising the final resume anchor, chapter focus and themed progress styling at both widths. |
| `npm.cmd run typecheck` | **Passed** after the final production build. |
| `npm.cmd run build` | **Passed**; all application routes built with TypeScript validation. |
| Runtime | Isolated FastAPI and Next.js processes launched by Playwright; API proxy, persistent writes, refresh/resume and publication exercised through actual browser interactions. |

PostgreSQL checks include the original RLS/storage/publication/AI contracts plus private action/progress rows, spoofed-user rejection, duplicate desired states, aggregate counts visible without private flags, chapter/story mismatch rejection, discovery pages, empty visual enrichment and rollback on conflicting established visuals. SQL execution is real; it does not run hosted Supabase Auth or Storage services or constitute a multi-connection PostgreSQL load test.

Browser journeys cover likes/bookmarks/follows across refresh, library inclusion/removal, published character notes, comic/webtoon reading, monotonic progress, profile resume with saved layout, non-overlapping discovery pages, URL refresh, search/genre/order and empty results. They verify loaded panel image dimensions, prevent duplicate rendering, check viewport overflow, and retain the existing contributor-to-publication path, failure/retry and versioned panel actions.

Reader screenshots from the final fixture walkthrough: [desktop](screenshots/phase-3-reader-desktop.png), [mobile](screenshots/phase-3-reader-mobile.png). [Discovery](screenshots/phase-3-discovery-desktop.png) shows disposable, hand-written pagination fixtures. These images demonstrate UI/persistence, not live AI quality. Chapter navigation moves focus to the selected chapter; screenshot capture scrolls to the page top to avoid offscreen fixed-element artifacts.

The initial browser run found a rapid filter-change race, which was fixed by retaining the pending URL filter state. The older screenshot check also assumed a short feed; it now scrolls each lazy cover into view before decoding it. The complete rerun passed. Existing upstream Starlette/httpx and Node color-environment warnings remain non-fatal.

## Real versus mocked versus unverified

| Integration | Status |
| --- | --- |
| Local database/files | **Real and exercised.** SQLite persists actions, progress, stories, drafts, chapter memory and uploaded files; restart persistence is tested. Demo identity is shared, not real account authentication. |
| PostgreSQL migrations/security | **Real SQL execution, simulated service schemas.** PGlite executes all four migrations and role/RLS checks. Hosted network/Auth/Storage behavior is not verified by this. |
| Hosted Supabase | **Unverified live.** The opt-in two-account test was extended to include community idempotence, libraries, private progress and discovery. Requires a disposable migrated project and the documented test accounts. |
| Gemini | **Mocked only; live unverified.** SDK/configuration/continuity/workflow tests use fixtures. Requires a backend key and unpaid-project confirmation for the explicit live test. Real quality, model/account availability and semantic continuity remain unverified. |
| SDXL / ComfyUI | **Mocked only; live unverified.** Native ComfyUI and the other adapters are automatically tested without installation. Actual rendering, latency, image quality and RTX 4050/6 GB VRAM behavior remain unverified. Downloads were not required or changed. |
| Automated AI demo | Visibly marked mocked text and flat-color SDXL fixtures. They demonstrate workflow behavior, not successful model inference. Production never silently substitutes these fixtures. |

Live tests are skipped unless explicitly opted in. Gemini uses `STORYVERSE_LIVE_GEMINI_TESTS=1`; local images use `STORYVERSE_LIVE_SDXL_TESTS=1` with the selected adapter; Supabase uses `STORYVERSE_LIVE_TESTS=1` and two test accounts. Configuration alone is not verification. See [README](../README.md) and [local SDXL setup](local-sdxl.md).

## Limits and handoff

Reading progress is an explicit chapter cursor and furthest completed position, not inferred scroll completion. Marking chapter N read records progress through N. Pagination is deterministic on an unchanged dataset; concurrent publications/engagement can move offset-based results. Counts update on reads/actions, without realtime subscriptions. Following provides a library, not email/push alerts.

Structural canon checks and stable visual prompts cannot guarantee semantic consistency or identical generated faces. Review remains required. Existing bounded context/canon quotas remain. Runtime GPU work may continue after an HTTP timeout; wait until idle before retrying. Private orphan cleanup, moderation, abuse controls and background queues remain outside this scope.

Offline startup, a repeatable presentation and troubleshooting are documented in the [demo guide](demo-guide.md). Historical [Phase 1](validation.md), [Phase 2](phase-2-validation.md) and [SDXL/ComfyUI](sdxl-validation.md) reports are retained. Phase 3 does not claim live provider or hosted integration verification.
