from fastapi import HTTPException


class SupabaseAIMixin:
    async def generation_source(self, token, user_id, draft_id):
        result = await self.rpc("generation_source", token, {"p_draft_id": draft_id})
        if not result:
            raise HTTPException(404, "Draft not found")
        return result

    async def context_snapshot(self, token, story_id, terms):
        result = await self.rpc("story_context", token, {"p_story_id": story_id, "p_terms": terms})
        if not result:
            raise HTTPException(404, "Story not found")
        return result

    async def reserve_generation(self, token, user_id, draft_id, request_id, kind, revision, signature, settings):
        return await self.rpc("ai_reserve", settings.supabase_service_role_key, {"p_owner_id": user_id,
            "p_draft_id": draft_id, "p_request_id": request_id, "p_kind": kind, "p_revision": revision, "p_signature": signature,
            "p_limits": {"global_daily": settings.ai_global_daily_limit, "user_daily": settings.ai_user_daily_limit,
                "per_minute": settings.ai_requests_per_minute, "concurrency": settings.ai_global_concurrency,
                "lease_seconds": (settings.worker_lease_seconds + 60 if settings.sdxl_execution == "worker" else settings.sdxl_timeout_seconds + 60) if kind == "image" else settings.ai_timeout_seconds * 2 + 30}})

    async def finish_generation(self, token, user_id, job_id, payload, metadata, memory_only=False):
        return await self.rpc("ai_finish", self.settings.supabase_service_role_key, {"p_owner_id": user_id,
            "p_job_id": job_id, "p_payload": payload, "p_metadata": metadata, "p_memory_only": memory_only})

    async def fail_generation(self, token, user_id, job_id, code):
        await self.rpc("ai_fail", self.settings.supabase_service_role_key, {"p_owner_id": user_id, "p_job_id": job_id, "p_code": code})
