# Phase 2 plan update · Gemini text and local SDXL images

Preserve the existing UI, stored stories, Gemini abstraction, context/Bible, draft versions and explicit publication approval.

1. **Text stays on Gemini.** Backend-only environment credentials, unpaid-project confirmation, structured chapter output and existing mocked tests remain. Generated chapter output supplies the comic-panel prompts.
2. **Add optional local SDXL inference.** Implement a backend `ImageProvider` adapter for AUTOMATIC1111, native ComfyUI or a documented local JSON inference endpoint. Default off; loopback endpoints only; no paid image API or automatic model downloads. Start with 768×768, 20 steps, batch size one, no refiner/high-resolution pass. ComfyUI submits a built-in workflow, polls history and retrieves its PNG, with tiled VAE decoding. Configure low-VRAM/offload behavior in the runtime.
3. **Generate images during review.** After text generation, users explicitly generate/regenerate individual panel images. Each successful action creates a new draft version, preserving the previous version. Images are independent of Gemini availability once prompts exist. Description regeneration remains a separate action.
4. **Reuse persistence and approval.** Validate image bytes, save through existing owner-scoped local/Supabase Storage uploads, persist panel prompt/model/seed/settings/provenance, and make generated media public only in the publication transaction. Preserve manual uploads and version conflicts.
5. **Bound local GPU work.** One active image request globally across API workers, durable job/idempotency checks, bounded response sizes/timeouts and no automatic image retries. Check runtime busy state after ambiguous timeouts; keep descriptions/previous images when unavailable.
6. **Preview both formats.** Show private generated images in Studio and approved images in Webtoon/Comic Book readers, with clear labels for descriptions, unavailable images and mocked fixtures.
7. **Validate and document.** Mock SDXL for provider/API/browser/database tests. Add a separate explicit opt-in live SDXL test and local endpoint contracts/setup. No local runtime was discovered on ports 7860/8188/8002 during initial inspection. Do not claim local inference, VRAM use, latency or image quality verified without an actual live run.

Workflow: **Gemini text → preview/edit/regenerate → optional local SDXL panels → review → explicit approval → atomic publication**. Unavailable SDXL leaves a functional text/description workflow.

Implementation status: completed against configurable local endpoints, with mocked provider/API/browser coverage and actual PostgreSQL migration tests. See [setup](local-sdxl.md) and [validation](sdxl-validation.md). Live Gemini, SDXL inference and hosted Supabase remain unverified.
