import hashlib
import json
import logging
from uuid import uuid4
from fastapi import HTTPException
from .context import StoryContextBuilder
from .providers import GeminiProvider, GenerationError
from .amd import AMDProvider
from .schemas import ComicPrompt, GeneratedChapter, MemoryOutput, merge_bible, narrative_hash

log = logging.getLogger("storyverse.generation")


class AIService:
    def __init__(self, settings, repo, provider=None):
        self.settings, self.repo = settings, repo
        self.provider = provider or (AMDProvider(settings) if settings.ai_mode == "amd" else GeminiProvider(settings))
        self.context = StoryContextBuilder(repo, settings.ai_context_chars)

    def status(self):
        s = self.settings
        configured = bool(s.ai_mode == "gemini" and s.gemini_api_key and s.gemini_free_tier_confirmed
            and (s.app_mode != "supabase" or s.supabase_service_role_key))
        from .providers import FREE_TEXT_MODELS
        configured &= s.gemini_model in FREE_TEXT_MODELS
        if s.ai_mode == "amd":
            configured = bool(s.amd_api_key and (s.app_mode != "supabase" or s.supabase_service_role_key))
        model = s.amd_model if s.ai_mode == "amd" else s.gemini_model
        return {"enabled": configured, "mode": s.ai_mode, "model": model if configured else None,
            "mocked": bool(getattr(self.provider, "is_test_fixture", False)), "images": "descriptions_only",
            "user_daily_limit": s.ai_user_daily_limit, "per_minute": s.ai_requests_per_minute}

    async def generate(self, token, user_id, draft_id, request_id, revision, panel_index=None, memory_only=False):
        # Ownership is verified even when AI isn't configured; no key/status leak
        # changes which private drafts a user can inspect.
        source = await self.repo.generation_source(token, user_id, draft_id)
        if not self.status()["enabled"]:
            raise GenerationError("not_configured", "The selected text provider isn't configured. Your contribution is saved; demo preview remains available explicitly.", 503)
        kind = "memory" if memory_only else "panel" if panel_index is not None else "chapter"
        if panel_index is not None and (source.get("source") != "ai_generated" or not 0 <= panel_index < len(source.get("ai_data", {}).get("panels", []))):
            raise HTTPException(422, "This panel does not exist")
        signature = hashlib.sha256(f"{draft_id}:{kind}:{revision}:{panel_index}".encode()).hexdigest()
        job = await self.repo.reserve_generation(token, user_id, draft_id, request_id, kind, revision, signature, self.settings)
        if job["status"] == "succeeded":
            return {"id": job["result_draft_id"], "replayed": True}
        if job["status"] == "failed":
            raise GenerationError(job.get("error_code") or "failed", "This generation failed. Your saved draft is unchanged. Retry with a new request.", 409)
        # The initial reservation and an in-progress replay both return running.
        # A database-issued claim ensures only its creator calls the provider.
        if not job.get("claimed", True):
            raise HTTPException(409, "This generation is already running. Please wait.")
        try:
            c = source["contribution"]
            if not c["text"].strip() and panel_index is None and not memory_only:
                raise GenerationError("idea_required", "Add a text idea before using AI. Uploaded media is preserved but isn't sent to the text model.", 422)
            context = await self.context.build(token, source["story_id"], c["text"], c["direction"])
            if context["story_version"] != source["base_version"]:
                raise HTTPException(409, "The story changed. Read the latest chapter before continuing.")
            if memory_only:
                context["final_reviewed_chapter"] = {"title": source["title"], "narrative": source["narrative"]}
                # Analysis doesn't need the original contributor idea beyond the
                # final approved words, nor full previous chapter excerpts.
                context.pop("contributor_idea", None)
                context["recent_relevant_chapters"] = []
                context["earlier_summaries"] = []
                self.check_context_size(context)
                result = await self.provider.structured("analyze_reviewed_chapter", context, MemoryOutput)
                memory = result.value.model_dump()
                payload = {"memory": memory, "bible_after": merge_bible(context["story_bible"], result.value.additions),
                    "memory_hash": narrative_hash(source["title"], source["narrative"]), "memory_revision": revision}
            elif panel_index is not None:
                context.pop("contributor_idea", None)
                context["recent_relevant_chapters"] = []
                context["earlier_summaries"] = []
                context["reviewed_chapter"] = {"title": source["title"], "narrative": source["narrative"]}
                context["existing_panels"] = [{k:v for k,v in p.items() if k != "image"} for p in source["ai_data"]["panels"]]
                context["panel_to_regenerate"] = panel_index + 1
                self.check_context_size(context)
                result = await self.provider.structured("regenerate_single_panel_description", context, ComicPrompt)
                payload = {**source["ai_data"], "title": source["title"], "narrative": source["narrative"]}
                payload["panels"] = [dict(p) for p in payload["panels"]]
                payload["panels"][panel_index] = result.value.model_dump()
                payload["memory_revision"] = 0 if payload.get("memory_hash") == narrative_hash(source["title"], source["narrative"]) else -1
            else:
                self.check_context_size(context)
                result = await self.provider.structured("continue_story", context, GeneratedChapter)
                # A second local validation protects the repository boundary even
                # if a future provider doesn't validate its own output.
                chapter = GeneratedChapter.model_validate(result.value.model_dump())
                payload = chapter.model_dump()
                payload.update(bible_after=merge_bible(context["story_bible"], chapter.memory.additions),
                    memory_hash=narrative_hash(chapter.title, chapter.narrative), memory_revision=0)
            model = result.model or self.status()["model"]
            if memory_only:
                # An operator may select Gemini after AMD generated the chapter.
                # Review analysis must not relabel the original narrative's origin.
                payload.update(memory_provider=self.provider.name, memory_model=model)
            else:
                payload["provider"] = self.provider.name
                payload["model"] = model
                payload["is_test_fixture"] = bool(getattr(self.provider, "is_test_fixture", False))
            metadata = {"provider": self.provider.name, "model": model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}
            result_id = await self.repo.finish_generation(token, user_id, job["id"], payload, metadata, memory_only)
            log.info("generation status=success job=%s kind=%s model=%s input_tokens=%s output_tokens=%s", job["id"], kind, metadata["model"], result.input_tokens, result.output_tokens)
            return {"id": result_id, "replayed": False}
        except (ValueError, KeyError) as exc:
            await self.repo.fail_generation(token, user_id, job["id"], "continuity_validation")
            raise GenerationError("continuity_validation", "The result conflicted with established story facts or was incomplete. Your previous draft is safe; retry or edit manually.") from exc
        except (GenerationError, HTTPException) as exc:
            code = getattr(exc, "code", "conflict")
            await self.repo.fail_generation(token, user_id, job["id"], code)
            log.info("generation status=failed job=%s kind=%s code=%s", job["id"], kind, code)
            raise
        except Exception as exc:
            await self.repo.fail_generation(token, user_id, job["id"], "internal")
            # Never log SDK exception text, raw prompts, responses or credentials.
            log.error("generation status=failed job=%s kind=%s code=internal", job["id"], kind)
            raise GenerationError("internal", "Generation failed. Your previous draft is safe; please try again.", 503) from exc

    def check_context_size(self, context):
        if len(json.dumps(context, ensure_ascii=False).encode()) > self.settings.ai_context_chars:
            raise GenerationError("context_limit", "This chapter and canon exceed the context limit. Shorten the draft before retrying.", 422)

    async def prepare_publish(self, token, user_id, draft_id, expected_version):
        d = await self.repo.generation_source(token, user_id, draft_id)
        if d["base_version"] != expected_version:
            raise HTTPException(409, "This draft belongs to a different story version")
        if not d["narrative"].strip():
            raise HTTPException(422, "Add a narrative before publishing")
        if d["status"] == "published" or d.get("source") != "ai_generated":
            return
        if d.get("ai_data", {}).get("memory_hash") == narrative_hash(d["title"], d["narrative"]):
            return
        # Analyze the final edited words before the transaction. If this fails,
        # publication does not occur. No model call happens inside the DB lock.
        await self.generate(token, user_id, draft_id, str(uuid4()), d.get("revision", 0), memory_only=True)
