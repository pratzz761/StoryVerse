# AMD Token Factory integration validation

Date: **18 October 2026**. Implementation and credential-free regression checks are complete. **Live AMD inference has not been verified.** The private backend environment currently has a blank `AMD_API_KEY`; no AMD-generated chapter or live provider success is claimed.

## Configuration and implementation

AMD is selected as the primary text provider in the private local environment, backend example templates and Render configuration:

```dotenv
AI_MODE=amd
AMD_API_KEY=
AMD_MODEL=DeepSeek-V4-Flash
AMD_BASE_URL=https://developer.amd.com.cn/radeon/api/v1
```

The endpoint, model and Bearer authentication format come from AMD's [official Model APIs guide](https://amd-aim.github.io/radeon-cloud-docs/guides/model-apis/), [authentication reference](https://amd-aim.github.io/radeon-cloud-docs/api/authentication/), [catalog reference](https://amd-aim.github.io/radeon-cloud-docs/api/models/) and [chat reference](https://amd-aim.github.io/radeon-cloud-docs/api/chat-completions/). They were not inferred from unrelated providers. Actual availability and account access still require a live catalog request with the operator's key. See [setup instructions](amd-token-factory.md).

`app/ai/amd.py` implements the existing `AIProvider` interface using the installed `httpx` dependency. Its native structured schema handling retains strict Pydantic validation. The shared service selects AMD or Gemini through `AI_MODE`; an AMD failure never calls Gemini. Fallback requires explicit operator selection of `AI_MODE=gemini` and a backend restart. Existing Gemini credentials/configuration were preserved privately.

Generation continues through the existing ownership checks, durable reservations/quotas, bounded context, canon comparison, new draft versions, individual panel-description regeneration, final-edit memory analysis and atomic approved publication. Provider/model provenance is saved with generated drafts. Review analysis records its own provider/model without relabeling the original chapter when the operator selects another provider. Public reporting and human moderation remain unchanged. No database migration or new dependency was needed. No SDXL, ComfyUI, image-job, worker, storage or publication implementation was changed.

Consent and loading/error labels now identify the configured text provider. Existing demo previews remain explicit; failures do not become fabricated AI results.

## Fresh automated results

| Check | Actual result | Scope |
| --- | --- | --- |
| Complete backend suite | **149 passed, 5 skipped in 16.35 seconds**, exit 0 | Credential-free tests; provider HTTP/SDK calls mocked |
| Playwright desktop/mobile | **20 passed in 2.6 minutes**, exit 0 | Isolated SQLite/files, mocked providers; real browser navigation, review, approval and reader layouts |
| TypeScript | **Passed**, exit 0 | `npm.cmd run typecheck` |
| Next.js production build | **Passed**, exit 0 | `npm.cmd run build`; all routes compiled/generated |
| Deployment configuration checks | **Passed**, exit 0 | HTTPS, frontend rewrite, public-key restrictions and security headers |
| Five ordered migrations | **Passed**, exit 0 | Local PostgreSQL/PGlite RLS, ownership, quotas, idempotence, publication and remote queue assertions |
| Credential scan | **Passed** | Existing private credential values checked in memory against 97 source/test/documentation/template files; no matching values found |
| Live AMD chapter | **Not run: missing AMD_API_KEY** | No AMD request, model output, token usage or generation duration measured |
| Live Gemini, SDXL, hosted Supabase and deployed API | **Not rerun** | Their opt-in tests stayed skipped; prior live reports are historical evidence only |

The five backend skips are the explicitly opt-in AMD, Gemini, SDXL, hosted Supabase and deployed API tests. Backend output includes the existing Starlette/httpx deprecation warning. Browser output includes existing Node color-environment warnings. All 20 browser assertions passed; Windows test-server cleanup required terminating only the disposable Playwright server process trees before the runner exited successfully. No user-owned ComfyUI or application process was terminated.

AMD HTTP contract tests cover the official URL/header, catalog cache, exact/free/JSON-capable model selection, strict-schema and JSON-object modes, nested schema bounds, prompt separation, token/context bounds, malformed output/envelopes, oversized responses, refusal, authentication, quota, redirects, timeout and network failure. They assert no automatic retry or Gemini call. API workflow tests cover AMD provenance, chapter/panel/memory results, original draft preservation, edited publication, publication replay and explicit Gemini review of an AMD chapter without changing its provenance. The browser's two new AMD consent cases use mocked health metadata; they are not live AMD generations.

Commands executed from the appropriate directories:

```powershell
# backend: all live opt-ins disabled
.\.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider

# frontend
npm.cmd run typecheck
npm.cmd run test:config
npm.cmd run build
npm.cmd run test:db
npm.cmd test
```

## Remaining live check and limitations

The operator was asked to add `AMD_API_KEY` privately to `backend/.env` and confirm that it belongs to AMD Radeon Cloud Token Factory at the documented origin. The key remains blank at this report's final check. If the operator's portal instead supplies another API origin or model, obtain its official documentation before transmitting credentials; do not guess or reuse the key against an unrelated service.

Once configured, run the opt-in command in [AMD setup](amd-token-factory.md#tests). That test performs one actual AMD chapter request, validates its narrative, 2–4 panels, structured memory and canon merge, and cannot use Gemini. Record the returned model, actual outcome, latency and any sanitized failure here after executing it. **No live response exists yet**, so strict-schema compatibility with the actual runtime and generated prose/continuity quality remain unverified. Live Studio persistence/publication using AMD and hosted deployment inference also remain unverified.

The AMD input preflight uses a conservative UTF-8 byte budget because the referenced API does not document a tokenizer/count endpoint. This can reject a long context earlier than Gemini's actual token counting. Provider refusals, Pydantic validation and canon checks do not prove semantic moderation or perfect character continuity. The existing explicit review/approval and human moderation controls remain necessary.

No paid instance or service was created, and no public deployment was performed. No API credential, fingerprint, request header value or raw provider error is included in this report.
