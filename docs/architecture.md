# Architecture and API · Phase 3

The existing Next.js UI reverse-proxies `/api` to FastAPI. Supabase JS manages browser sessions; FastAPI verifies bearer tokens with Supabase Auth, then forwards caller JWTs for ordinary data/storage access. Demo persistence uses SQLite and local files with an explicitly shared persona. Persistence (`APP_MODE`) and generation (`AI_MODE`) are independent.

## Generation boundary

`AIProvider.structured(task, data, schema)` returns a validated Pydantic model and usage metadata. `GeminiProvider` implements it through the official `google-genai` SDK: model discovery, token counting, JSON Schema output, output limits, overall timeout and bounded retries. `ImageProvider.generate(description, appearance_context)` returns bytes/MIME/metadata for the existing upload pipeline. Its optional `LocalSDXLProvider` calls loopback AUTOMATIC1111, native ComfyUI or the [generic local contract](local-sdxl.md). Images default disabled; no paid image API or GPU runtime is bundled.

`PanelImageService` operates independently of the Gemini key once panel prompts exist. It combines panel/appearance notes, reserves an `image` job, requests one PNG, validates it with Pillow, saves an owner-private upload and creates a new draft version with image metadata. A new seed is used for individual regeneration. It never publishes. Runtime errors retain descriptions/previous images; fixture images are labeled separately. Configuration reports `runtime_status: not_verified`, not an inference-success claim.

`SDXL_API_FLAVOR=comfyui` selects native ComfyUI inside the same local provider. `comfyui.py` builds a core-node SDXL workflow with one latent/sampler, tiled VAE decode and a temporary preview output; it checks `/queue`, submits `/prompt`, polls `/history/{prompt_id}` and retrieves `/view` bytes. The shared provider owns loopback validation, response bounds, timeout and PNG validation. Polling stays inside the existing durable image reservation. This adapter neither retries submission nor interrupts unrelated runtime jobs. AUTOMATIC1111/generic behavior and the database/storage/publication contracts are preserved.

Chapter output contains title, readable narrative with embedded dialogue, dialogue/scene breakdowns, 2–4 panel descriptions, summary and canonical additions. The Story Bible tracks immutable character/location descriptions, relationships, world rules, events, chronology and open/resolved plotlines. New facts append; conflicting existing descriptions are rejected. Historical unresolved items remain in canon with separate resolution records. Structural checks cannot prove all prose-level semantic consistency, so contributor review remains essential.

The Context Builder retrieves the premise, stored summaries, Bible, three recent chapters and up to two lexically relevant older excerpts. Outgoing UTF-8 context size and provider input tokens are bounded. It does not send all chapter bodies for a long story. Earlier manual/sample summaries are marked `extractive`. JSON text is untrusted contextual data, never system instructions. No tools, upload bytes, account metadata or other private drafts enter the model request.

## Versioning and publication

1. The existing contribution endpoint saves the original idea/direction/uploads and returns an unchanged private demo draft, preserving Phase 1 behavior.
2. An explicit AI action reserves a durable job against its owner's current draft revision. Unique request IDs and active leases prevent duplicate concurrent generation; daily/minute quotas include failed reservations.
3. The provider result passes schema/continuity validation, then creates a new draft with `parent_draft_id`. The original saved draft remains intact. A changed draft or story rejects the result. Single-panel description regeneration copies reviewed text/other panels and drops that panel's stale image in the new version. Image regeneration replaces only that image; previous draft versions retain their files.
4. Content edits increment `revision`. Generated memory records the content hash/revision it describes. Before an edited AI draft is published, the final saved words receive structured summary/canon analysis. Failure preserves the private draft.
5. Explicit approval invokes the original publication contract: owner check, locked draft/story, exact base/expected version and unique chapter position. AI drafts additionally require current memory revision. Chapter, prompts, summary, canonical memory, version increment, draft status and media visibility commit atomically. No provider call runs inside that transaction.

Repeated AI publication returns its existing receipt. Repeated demo publication retains the Phase 1 409 behavior. No generation endpoint can publish. All prose/captions are React text, without HTML interpretation.

## Persistence and permissions

Migration 2 adds draft `revision`, `parent_draft_id`, `ai_data`; chapter `summary`, `comic_prompts`, `ai_metadata`; `story_bibles`; and `generation_jobs`. It backfills extractive summaries and a chapter-title timeline without altering previously published narrative. Multiple draft versions may reference one original contribution.

Migration 3 adds the image job kind, wraps the existing service-only reserve/finish functions, validates referenced image ownership, and enforces one active image job across users. Its chapter trigger publishes generated uploads and inserts panel rows in reserved positions 1001–1004, inside the original publication transaction. Manual attachments stay separate from generated image metadata. Caller-scoped private storage and published-file access remain unchanged. Images created before a stale-result failure stay private; orphan cleanup is deferred.

Browser roles can read only their own jobs/drafts/contributions. Published canon is public. Provider payload writes and AI reservation/result/failure RPCs are restricted to Supabase's backend service role; FastAPI supplies the verified user ID. These RPCs independently check ownership, status, revision and story version. The service key is never used by the frontend. Ordinary operations retain caller JWTs and RLS. PostgreSQL advisory locks serialize quota reservation across workers; the chapter-memory trigger rejects any Bible that drops established facts. SQLite transactions implement the same contracts locally. Expired leases release concurrency slots, without silently rerunning an old request ID.

## HTTP API

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/health` | Persistence and AI capability/model/test-fixture status; no secrets |
| GET/PATCH | `/api/me` | Own profile; editable name/bio |
| GET | `/api/profiles/{id}` | Public profile fields |
| GET | `/api/me/stories` | Own created/contributed lists |
| GET/POST | `/api/stories` | Public feed; authenticated manual story creation |
| GET | `/api/discover?search=&genre=&sort=trending&page=1&page_size=12` | Paginated public discovery: items, total, page, page_size, has_next |
| GET | `/api/stories/{id}/engagement` | Public aggregate counts; caller's own like/bookmark/follow flags |
| POST | `/api/stories/{id}/interactions` | Authenticated desired state: `{"kind":"bookmark","active":true}`; idempotent |
| GET/POST | `/api/me/reading/{story_id}` | Own private cursor; write `{"chapter_id":"uuid","completed":true,"layout":"comic"}` |
| GET | `/api/stories/{id}/bible` | Published character traits, visual descriptions, relationships and events |
| GET | `/api/stories/{id}` or `/api/stories/{id}/chapters` | Published chapters, summaries, prompts, credits and media |
| POST | `/api/stories/{id}/contributions` | Private contribution and unchanged demo draft |
| GET | `/api/drafts` | Own unpublished versions |
| GET/PATCH | `/api/drafts/{id}` | Owner-only draft; edit title/narrative; revision included |
| POST | `/api/drafts/{id}/generate` | A new AI draft version |
| POST | `/api/drafts/{id}/panels/{index}/regenerate` | New version replacing one description, with zero-based index |
| POST | `/api/drafts/{id}/panels/{index}/image` | New private version generating/regenerating one local SDXL image; same request body, independent of Gemini |
| POST | `/api/drafts/{id}/regenerate` | Original reset, restricted to demo drafts |
| POST | `/api/drafts/{id}/publish` | Explicit approval, expected version and final memory checks |
| POST | `/api/uploads` | Validated private multipart media |
| GET | `/api/uploads/{id}/file` | Owner while private; public after approval/publication |

Generation body:

```json
{"request_id":"new-uuid-per-explicit-action","expected_revision":0,"consent":true}
```

Success: `{"id":"new-draft-uuid","replayed":false}`. A replay returns the completed result ID. GET that draft for `ai_data`, source, revision, parent link and separate sanitized text/image-generation error codes. An in-progress, failed or expired request is not automatically rerun; an explicit fresh retry uses a new ID.

Publication body: `{"expected_version":3,"approved":true}`. Editing AI text may require an additional analysis reservation before the atomic publication.

Statuses: validation 422; unsupported media 415; oversized files 413; missing session 401; forbidden operation 403; inaccessible resource 404; stale/concurrent operation 409; app/provider quota 429 with `Retry-After`; invalid/contradictory output 502; provider/config unavailable 503; provider timeout 504. No response exposes credentials, prompts or raw SDK exceptions.

## Operational scope

Migration 4 adds `(user_id,story_id,kind)` unique interactions and `(user_id,story_id)` reading progress. RLS protects individual rows; a definer read function exposes only public aggregates plus `auth.uid()`'s flags. Desired-state actions use caller JWTs and an invoker RPC, with `ON CONFLICT DO NOTHING`. Reading writes use a guarded RPC that derives the caller from `auth.uid()`, validates the chapter/story pair and preserves the greatest completed position. Direct reading writes and cross-user interaction writes are denied. No service key is needed for community actions.

Discovery uses persisted likes, follows, chapter count, publication time and ascending ID as a deterministic trending order; recent uses publication time and ID. Search is a literal case-insensitive substring. Pagination bounds are 1–60 items; the legacy array feed stays available. Profiles return created, contributed, bookmarked, followed and reading lists. No activity notifications, personalized ranking or browser-only persistence is used.

Character JSON is backward compatible: old records gain empty trait/visual defaults on read. Merge checks reject changing established visual descriptions, preserve traits/relationships and append events. The chapter-memory trigger permits filling an unknown empty visual description while retaining containment checks for established facts. Publication updates canon atomically and leaves earlier narrative untouched. The curated three-chapter local sample has hand-written character notes, labeled as sample content.

The dated free-model allowlist and runtime model discovery are not billing detection. An operator must confirm an unpaid project; the app never manages billing. Context, schema or model changes may require budget adjustment. Usage logs contain IDs/model/token/error metadata, not private text. Default tests never call paid or live model services.

SDXL is synchronous and optional: fixed single-image requests, default 768×768/20 steps, bounded HTTP/image sizes, runtime busy checks and no automatic retries. Jobs share the existing durable user/global quotas. Low-VRAM/offload settings must be configured in the local runtime. A timed-out render may continue externally; the runtime must serialize all its clients. Local inference has not been verified on this machine.

Not included: a bundled GPU runtime/model weights, upload interpretation, a full semantic contradiction prover, canon editing UI, moderation, a background generation queue or upload cleanup worker. These are explicit future decisions, not automatic fallback services.
