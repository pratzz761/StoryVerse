# AMD Token Factory text generation

StoryVerse supports AMD Radeon Cloud Token Factory as its primary configured text provider. Gemini remains an explicit operator-selected fallback. Images still use the existing SDXL/ComfyUI integration; no image adapter changed.

## Official API contract

Checked on 18 October 2026 against AMD's [Model APIs guide](https://amd-aim.github.io/radeon-cloud-docs/guides/model-apis/), [authentication reference](https://amd-aim.github.io/radeon-cloud-docs/api/authentication/), [model catalog reference](https://amd-aim.github.io/radeon-cloud-docs/api/models/) and [chat completions reference](https://amd-aim.github.io/radeon-cloud-docs/api/chat-completions/). The [AMD developer contest guide](https://github.com/AMD-DEV-CONTEST/Radeon-hackathon-2026-07/blob/main/Radeon-Cloud-User%20Guide/README.md) also links this Token Factory.

- Base URL: `https://developer.amd.com.cn/radeon/api/v1`
- Model: `DeepSeek-V4-Flash` (documented shared model, not an invented alias).
- Authentication: `Authorization: Bearer <AMD_API_KEY>`, server-side only.
- Catalog: `GET /models`; generation: `POST /chat/completions`.

Use the **Public Free Model APIs** section of [AMD Token Factory](https://developer.amd.com.cn/radeon/modelapis). No dedicated instance, credits, paid service or checkpoint download is needed. The similarly named `tokenfactory.cn` is a different service; do not send this key there. Confirm the model card's base URL/model match before configuring a credential. Review AMD's [API terms](https://amd-aim.github.io/radeon-cloud-docs/api/terms/) before sending story data.

## Private backend configuration

Add these values to the ignored `backend/.env`, or Render's private environment editor. Never put the key in frontend variables, source files, screenshots, logs or chat. Preserve the existing `.env`; do not overwrite it from the example.

```dotenv
AI_MODE=amd
AMD_API_KEY=
AMD_MODEL=DeepSeek-V4-Flash
AMD_BASE_URL=https://developer.amd.com.cn/radeon/api/v1
```

Fill only the private key value, then restart FastAPI from `backend/`. OS environment variables take precedence over `.env`. Templates intentionally leave the key blank. `/api/health` reports configuration, not proof of successful inference. Backend settings hide the key in their representation; outbound credentials are headers, never query parameters. HTTPS is required, redirects and environment proxies are disabled for the production HTTP client.

To use the existing Gemini fallback, explicitly set `AI_MODE=gemini`, retain `GEMINI_API_KEY`, `GEMINI_MODEL` and `GEMINI_FREE_TIER_CONFIRMED=true` for the previously confirmed unpaid Google project, then restart. Set `AI_MODE=demo` to turn real text generation off. **There is no automatic failover:** an AMD error does not call Gemini, consume Google's quota or turn into a demo result. Changing providers affects future operations; saved drafts and published chapters retain their recorded generation model/provider. Analysis of final edited prose uses the currently selected provider.

## Structured output, limits and workflow

The adapter implements the existing `AIProvider.structured()` interface with `httpx`; no new dependency is needed. It caches the documented catalog for five minutes and requires the exact model ID, `free: true` and JSON capability before submitting a chapter. Missing/retired/non-free models fail visibly. Dedicated paid endpoints are not provisioned by this application.

Models advertising `structured_outputs: true` receive OpenAI `response_format.type=json_schema` with a strict schema: all object keys required, no defaults, no additional properties, retained nested refs and collection/string bounds. A model advertising only JSON-object output receives `json_object` plus the same schema in trusted instructions. This capability selection stays within AMD. The unchanged Pydantic chapter, panel and memory schemas validate every result locally. Markdown fences, incomplete/overlong chapters, unexpected model IDs, safety refusals and malformed usage fail instead of being repaired into apparently valid content.

The shared Story Bible context, immutable descriptions/visual cues, 2–4 comic-panel descriptions, durable quota reservations, ownership, idempotency, draft revisions, edit analysis and explicit publication approval all remain in the existing service. Moderation/reporting controls are unchanged. Structured validation and canon comparison do not prove semantic safety or perfect narrative continuity; contributors still review before publication.

AMD has no preflight tokenizer endpoint in the referenced API. Its preflight budget conservatively uses UTF-8 bytes of instructions/schema/context plus 256 framing units against `AI_MAX_INPUT_TOKENS`; this is a conservative estimate, not measured tokens. Long contexts may be rejected earlier than Gemini's counted-token path. The reported input/output usage is also checked after generation. Defaults remain 12,000 input budget, 4,096 output tokens and a 45-second operation timeout. No tools, uploaded media, reasoning options, automatic HTTP retries or provider switching are sent. Quota/auth/network/timeout errors use sanitized messages; user-triggered retries receive fresh reservations. A timed-out provider call may still consume remote quota.

## Tests

Normal tests mock HTTP and never need an AMD key:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_amd_provider.py -q
```

The opt-in live test sends **one actual chapter request** directly to AMD, validates chapter/panels/memory and checks canon merging. It does not publish or call Gemini/SDXL. Run only after privately configuring the free shared model:

```powershell
$env:STORYVERSE_LIVE_AMD_TESTS="1"
.\.venv\Scripts\python.exe -m pytest tests/test_amd_live.py -q --durations=1 --tb=no -p no:cacheprovider
Remove-Item Env:STORYVERSE_LIVE_AMD_TESTS
```

Use `--tb=no` for live credentials to avoid exposing provider internals through diagnostic tracebacks. API exceptions are deliberately sanitized. See [AMD validation results](amd-validation.md) for actual execution status; credentials alone never enable a live test.
