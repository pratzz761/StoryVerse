# Phase 2 implementation and validation report

Date: **17 October 2026**. Environment: Windows, Node.js 24.20.0, Python 3.13.5, Next.js 16.4.2, `google-genai` 2.31.0, Microsoft Edge via Playwright. Phase 1 was extended in place; its visual layout and original tests were retained. This report records the initial Gemini implementation; the subsequent requested local-SDXL extension and current aggregate results are in [SDXL validation](sdxl-validation.md).

## 1. Features implemented

| Feature | Implementation and verification status |
| --- | --- |
| Gemini text provider | Official SDK, `GEMINI_API_KEY`, configurable allowlisted Flash-Lite model, runtime model discovery, token counting, structured JSON Schema/Pydantic output. **SDK calls mocked in tests; live key/model round trip unverified.** |
| Provider abstraction | `AIProvider` contract separates provider behavior from context, persistence and UI. No automatic provider or paid-model switching. |
| Story continuation | Premise, genre/tone, canonical facts, structured history, recent/relevant excerpts, contributor idea and creative direction form the bounded context. **Tested with fixtures and a long-history case.** |
| Story Bible | Characters/descriptions/relationships, locations, world rules, timeline, events and open/resolved plotlines persist. Existing descriptions cannot be overwritten. Canon updates atomically on successful publication, not on generation. **Local and PostgreSQL tests pass.** |
| Chapter draft | Title, narrative with embedded dialogue, dialogue/scene notes, 2–4 panel prompts and summary. Draft preview supports title/narrative edits and save. **Workflow and browser fixtures tested.** |
| Regeneration | A new chapter version or single-panel version links back to the previous saved draft. Existing saved text, other prompts and uploads remain intact. In-flight edits reject stale results. **API and browser tested.** |
| Approval/publication | Explicit contributor approval remains mandatory. Edited AI content receives final-text summary/canon analysis before publication. Unique positions, row locks, version/revision checks and idempotent AI receipts prevent duplicate or stale publication. **API and PostgreSQL tests pass.** |
| Comic readers | Both Webtoon and Comic Book readers display labeled panel descriptions alongside uploaded media. Individual description regeneration is available in Studio. **Both browser widths/layouts tested.** |
| Demo compatibility | Original contribution/preview/reset/manual publication, filters, uploads, profile edits and draft recovery continue to work. AI failures expose the saved original as an explicitly labeled demo/manual draft with error and retry. **All original tests pass.** |
| Safeguards | Durable user/global quotas, rolling minute limits, one active job per user, global concurrency, idempotency, expiring leases, input/context/output limits, timeout, bounded retry and sanitized metadata logging. **Provider, workflow and database tests pass.** |

Test fixtures are visibly identified in Studio and published reader labels. No mock response or placeholder image is presented as a real Gemini result.

## 2. Files and APIs modified

Backend additions under `backend/app/ai/`:

- `providers.py`: `AIProvider`, Gemini SDK adapter, free-model allowlist, errors and description-only image boundary.
- `schemas.py`: generated chapter, dialogue, scenes, prompts, summaries and canonical schemas; append-only Bible merge and content hashes.
- `context.py`: reusable bounded Story Context Builder and lexical relevance terms.
- `service.py`: ownership-first orchestration, reservations, validation, versioned generation, panel regeneration and final-text analysis.
- `local_store.py` / `supabase_store.py`: persistent job/context/result contracts for both repositories.

Existing backend changes: `config.py`, `models.py`, `main.py`, `demo.py`, `supabase.py`, `.env.example`, requirements and dependency snapshot. Original repositories and endpoints were reused.

New endpoints:

- `POST /api/drafts/{id}/generate` — request UUID, expected draft revision and explicit data-sharing consent; returns a new/replayed draft ID.
- `POST /api/drafts/{id}/panels/{index}/regenerate` — zero-based panel index, same request contract; creates a separate version.

Enhanced endpoints: health reports capabilities without secrets; draft reads include AI data/revision/parent/error; publication analyzes edited AI content and retains atomic conflict protection; story reads include summary, prompt and provenance data. The original `/regenerate` remains a demo-only reset and cannot overwrite an AI version.

Frontend changes: existing Continue Story, Studio and Story Room components; reusable `comic-descriptions.tsx`; additive CSS and types; truthful demo notices/opening-story guidance; a longer API proxy timeout. No frontend runtime dependencies were added and no redesign was performed. Setup, API/architecture, historical validation links and new tests were updated.

## 3. Database changes

Additive migration: [202610170002_ai_storytelling.sql](../supabase/migrations/202610170002_ai_storytelling.sql).

- Draft revision, parent-version link and protected structured AI payload; multiple versions can reference the original contribution.
- Published summary, comic descriptions and provider/test provenance.
- Public, published-only `story_bibles` state and owner-readable/private `generation_jobs`.
- Extractive summary and chapter-title timeline backfill without changing published prose.
- Content revision trigger and transactional canonical-memory trigger.
- Caller-scoped context/source functions; service-role-only AI reserve/finish/fail functions.
- Database-wide reservation lock, daily/minute counts and expiring concurrency leases.
- Enhanced original publication RPC with final-memory revision check, preserved ownership/version guards and idempotent AI receipts.

Browser roles cannot update AI payloads, job outcomes, usage limits or canonical facts. Existing ordinary user operations still use caller JWTs and RLS. Only protected AI persistence RPCs require the backend-only Supabase service role key. Both actual migrations were executed in PostgreSQL/PGlite, with synthetic substitutes for Supabase-owned schemas. Hosted Auth/Storage services were **not** exercised.

## 4. Tests executed and results

| Command/check | Result |
| --- | --- |
| Backend dependency installation | Passed; official SDK installed; `requirements.lock.txt` refreshed |
| `python -m pytest -q` in backend virtualenv | **32 passed, 2 skipped**; live opt-in flags explicitly disabled during the credential-free rerun |
| `npm.cmd run typecheck` | Passed |
| `npm.cmd run build` | Passed; all application routes built |
| `npm.cmd run test:db` | Passed; both actual migrations and policy/publication checks |
| `npm.cmd test` | **10 passed**: 6 original Phase 1 journeys plus 4 AI journeys across desktop/mobile |
| Runtime | FastAPI and production Next.js both launched; same-origin API proxy verified |
| Live Gemini test | Skipped; no key and explicit live-test opt-in supplied |
| Live Supabase test | Skipped; no project/test-account credentials supplied |

Backend coverage includes the original nine API tests, eight provider/schema/canon tests, eleven AI workflow/context/security tests and four credential-configuration tests. It covers SDK schema/limits, 429 without fallback, timeout, bounded temporary retry, invalid output, conflicting established descriptions, bounded long-history context, separate draft versions, panel-only changes, final edited-memory analysis, approval, idempotent publication, one provider call under concurrency, revision changes during generation, ownership/auth failures, quota persistence after restart and failed-call draft preservation. Configuration tests prove that the key loads from the backend environment, stays out of settings representations, is blank in the example template, and is not needed to start the app or preserve a contribution after a rejected AI request. Missing-key generation does not construct or call the live SDK.

Database coverage includes the original grants/RLS/storage cases plus protected provider writes, atomic quota reservation, duplicate request claims, draft revision/memory checks, prompt persistence and repeat-safe AI publication. Browser tests cover progress-to-preview, saved edits after refresh, previous-version links, panel regeneration, explicit publication, both reading modes and provider-quota failure/retry. They check viewport overflow at 1440px and 390px.

The existing upstream Starlette TestClient/httpx deprecation warning remains; assertions pass. Default tests make **no real model calls**, paid or unpaid.

Screenshots: [desktop AI Studio](screenshots/phase-2-ai-studio-desktop.png), [mobile AI Studio](screenshots/phase-2-ai-studio-mobile.png). These are isolated test fixtures, clearly labeled in the image; they do not demonstrate live Gemini quality.

## 5. Real Gemini status and free-tier verification

**Implemented, SDK-validated and mocked end to end; not live-verified.** No live Gemini credentials were used. The selected default is `gemini-3.5-flash-lite`; `gemini-3.1-flash-lite` is another verified configuration option. Google's current [model catalog](https://ai.google.dev/gemini-api/docs/models) and [pricing](https://ai.google.dev/gemini-api/docs/pricing) were checked on the report date. At runtime, model discovery checks availability for the configured key before generation. Real availability, latency, prose quality and semantic consistency for a specific account still require the opt-in live test.

During the later credential audit, a key-like assignment was found appended to `.env.example` and removed without being used. The template now contains exactly one empty `GEMINI_API_KEY=` entry, protected by a regression test. No live call was made from that value. If it was a real key, rotate it. This does not change the unverified live-integration status.

The app cannot determine whether an API key's project has paid billing enabled. `GEMINI_FREE_TIER_CONFIRMED` is an operator attestation, not billing introspection. An unpaid project must be maintained for zero-cost use; application quotas alone cannot make a billed project free. The app never enables billing or silently selects a paid model/provider.

To verify: follow README's AI Studio setup, set backend credentials/unpaid confirmation, then explicitly enable `STORYVERSE_LIVE_GEMINI_TESTS=1` and run `tests/test_gemini_live.py`. A key alone never triggers live automated tests. Supabase has a separate opt-in two-account test.

## 6. Image availability and limitations

**Updated by the local SDXL extension:** real image generation remains disabled by default. An optional backend adapter now calls local AUTOMATIC1111 or a generic local SDXL inference endpoint; no paid image API is used. Its automated tests mock inference. Local GPU inference has not been verified. See [setup](local-sdxl.md) and [current validation](sdxl-validation.md).

Panel descriptions are real Gemini text when configured, or visibly mocked text in tests. They are never presented as raster artwork. Without SDXL, readers show “No image generated.” With SDXL configured, Studio can generate/regenerate one panel image into a new private draft version. The existing storage and approval workflow handles generated files. Mocked test PNGs are visibly labeled. There are no paid image calls or image-generation credentials.

## 7. Remaining issues and verification limits

- Live Gemini and hosted Supabase round trips require credentials and remain unverified. Phase 2 Supabase RPC/policy behavior was exercised in PostgreSQL, not through a hosted project.
- Structural checks preserve canonical facts, but do not prove that arbitrary narrative prose has no semantic contradiction. Contributor review is still required.
- Lexical retrieval is lightweight; it is not semantic vector retrieval. Very large canonical state can hit explicit memory/context bounds rather than silently discarding facts.
- The free tier may use submitted text/responses for product improvement and human review, subject to region-specific terms. The UI and README disclose this. See [Google's terms](https://ai.google.dev/gemini-api/terms#unpaid-services).
- Manual/sample chapters receive conservative extractive summaries and timeline entries. Full historical character extraction is not a separate unbounded migration/model job; new context and generated additions progressively enrich the Bible.
- Local image inference is implemented but remains live-unverified; no GPU runtime or weights are bundled. Upload interpretation/transcoding, canon editing, moderation, a background generation queue and orphan-upload cleanup remain outside this implementation.
- Generations are bounded synchronous API requests. Interrupted jobs keep their contributions and release concurrency capacity when the lease expires; there is no automatic background recovery or surprise retry.

## 8. Recommended Phase 3 priorities

1. Run the documented live Gemini and Supabase tests in dedicated unpaid/disposable projects, then evaluate continuity and writing quality with a small hand-reviewed story set.
2. Add reviewed Story Bible editing/conflict resolution and canon compaction for long-running stories, with provenance and version history.
3. Evaluate semantic chapter retrieval and summary quality against the existing bounded lexical baseline before introducing embeddings or extra services.
4. Add moderation, abuse controls, observability and private upload cleanup for a hosted social product.
5. Add asynchronous generation only if measured latency/capacity warrants it. Validate the optional local SDXL adapter on the user's hardware before claiming measured GPU compatibility or quality.

No Phase 3 implementation, hosted deployment, native mobile application or APK was created.
