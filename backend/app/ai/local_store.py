import json
import time
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from .schemas import StoryBible, extractive_summary, narrative_hash


class LocalAIMixin:
    def initialize_ai(self, db):
        for table in ("generation_jobs", "story_bibles"):
            db.execute(f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        for chapter in self.rows(db, "chapters"):
            if "summary" not in chapter:
                self.put(db, "chapters", {**chapter, "summary": extractive_summary(chapter["title"], chapter["narrative"]), "comic_prompts": []})
        existing = {b["id"] for b in self.rows(db, "story_bibles")}
        for story in self.rows(db, "stories"):
            if story["id"] not in existing:
                chapters = sorted([c for c in self.rows(db, "chapters") if c["story_id"] == story["id"]], key=lambda c: c["position"])
                data = StoryBible(timeline=[f"Chapter {c['position']}: {c['title']}" for c in chapters]).model_dump()
                self.put(db, "story_bibles", {"id": story["id"], "version": story["version"], "data": data})

    async def context_snapshot(self, token, story_id, terms):
        with self.db() as db:
            story = self.get(db, "stories", story_id)
            chapters = sorted([c for c in self.rows(db, "chapters") if c["story_id"] == story_id], key=lambda c: c["position"])
            recent = chapters[-3:]
            older = chapters[:-3]
            relevant = sorted(older, key=lambda c: sum(t in c["narrative"].lower() for t in terms), reverse=True)[:2] if terms else []
            for c in chapters:
                c.setdefault("summary", extractive_summary(c["title"], c["narrative"]))
            stored = next((b for b in self.rows(db, "story_bibles") if b["id"] == story_id), None)
            bible = stored["data"] if stored else StoryBible(timeline=[f"Chapter {c['position']}: {c['title']}" for c in chapters]).model_dump()
            return {"story": story, "bible": bible, "opening": chapters[0]["narrative"], "selected": relevant + recent,
                "outline": [{"position": c["position"], "title": c["title"], "summary": c["summary"]} for c in chapters]}

    async def generation_source(self, token, user_id, draft_id):
        with self.db() as db:
            d = self.owned_draft(db, draft_id, user_id)
            return {**d, "revision": d.get("revision", 0), "contribution": self.get(db, "contributions", d["contribution_id"])}

    async def reserve_generation(self, token, user_id, draft_id, request_id, kind, revision, signature, settings):
        stamp = time.time()
        with self.db() as db:
            d = self.owned_draft(db, draft_id, user_id)
            jobs = self.rows(db, "generation_jobs")
            existing = next((j for j in jobs if j["owner_id"] == user_id and j["request_id"] == request_id), None)
            if existing:
                if existing["signature"] != signature:
                    raise HTTPException(409, "This request ID belongs to a different generation")
                return {**existing, "claimed": False}
            if d["status"] != "draft" or d.get("revision", 0) != revision:
                raise HTTPException(409, "The draft changed. Reload before generating.")
            story = self.get(db, "stories", d["story_id"])
            if story["version"] != d["base_version"]:
                raise HTTPException(409, "A new chapter was published. Read it and start a new contribution.")
            active = [j for j in jobs if j["status"] == "running" and j["expires_at"] > stamp]
            if kind == "image" and any(j["kind"] == "image" for j in active):
                raise HTTPException(409, "One local image is already generating. Wait before retrying.")
            if any(j["owner_id"] == user_id for j in active):
                raise HTTPException(409, "A generation is already in progress. Your saved draft is safe.")
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today = [j for j in jobs if j["day"] == day]
            limited = len(today) >= settings.ai_global_daily_limit or sum(j["owner_id"] == user_id for j in today) >= settings.ai_user_daily_limit
            limited |= sum(j["owner_id"] == user_id and stamp - j["started_at"] < 60 for j in jobs) >= settings.ai_requests_per_minute
            limited |= len(active) >= settings.ai_global_concurrency
            if limited:
                raise HTTPException(429, "The application generation quota is reached. Wait before retrying; your draft is safe.", headers={"Retry-After": "60"})
            job = {"id": str(uuid4()), "owner_id": user_id, "draft_id": draft_id, "request_id": request_id, "kind": kind,
                "revision": revision, "signature": signature, "status": "running", "day": day, "started_at": stamp,
                "expires_at": stamp + (settings.sdxl_timeout_seconds + 60 if kind == "image" else settings.ai_timeout_seconds * 2 + 30), "result_draft_id": None, "error_code": None}
            self.put(db, "generation_jobs", job)
            return {**job, "claimed": True}

    async def finish_generation(self, token, user_id, job_id, payload, metadata, memory_only=False):
        with self.db() as db:
            job = self.get(db, "generation_jobs", job_id)
            d = self.owned_draft(db, job["draft_id"], user_id)
            if job["status"] != "running" or job["expires_at"] < time.time() or d["status"] != "draft" or d.get("revision", 0) != job["revision"]:
                raise HTTPException(409, "The draft changed during generation. Your saved draft is intact.")
            if self.get(db, "stories", d["story_id"])["version"] != d["base_version"]:
                raise HTTPException(409, "The story changed during generation. Your saved draft is intact.")
            if memory_only:
                result = {**d, "ai_data": {**d.get("ai_data", {}), **payload}}
            else:
                image_ids = [p["image"]["upload_id"] for p in payload.get("panels", []) if p.get("image")]
                self.owned_uploads(db, image_ids, user_id)
                result = {**d, "id": str(uuid4()), "parent_draft_id": d["id"], "source": "ai_generated", "revision": 0,
                    "title": payload["title"], "narrative": payload["narrative"], "ai_data": payload,
                    "created_at": datetime.now(timezone.utc).isoformat()}
            self.put(db, "drafts", result)
            self.put(db, "generation_jobs", {**job, **metadata, "status": "succeeded", "result_draft_id": result["id"]})
            return result["id"]

    async def fail_generation(self, token, user_id, job_id, code):
        with self.db() as db:
            job = self.get(db, "generation_jobs", job_id)
            if job["owner_id"] == user_id and job["status"] == "running":
                self.put(db, "generation_jobs", {**job, "status": "failed", "error_code": code})

    def publish_memory(self, db, story, draft, chapter):
        stored = next((b for b in self.rows(db, "story_bibles") if b["id"] == story["id"]), None)
        data = stored["data"] if stored else StoryBible().model_dump()
        ai = draft.get("ai_data", {})
        if draft.get("source") == "ai_generated":
            if ai.get("memory_hash") != narrative_hash(draft["title"], draft["narrative"]):
                raise HTTPException(409, "Review analysis is required for the edited chapter before publication")
            data = ai["bible_after"]
            chapter["summary"] = {**ai["memory"]["summary"], "source": "ai"}
            chapter["comic_prompts"] = ai.get("panels", [])
            generated = [p["image"]["upload_id"] for p in chapter["comic_prompts"] if p.get("image")]
            self.owned_uploads(db, generated, draft["owner_id"])
            self.make_public(db, generated)
            for i, panel in enumerate(chapter["comic_prompts"]):
                if panel.get("image"):
                    self.put(db, "panels", {"id": str(uuid4()), "chapter_id": chapter["id"], "upload_id": panel["image"]["upload_id"],
                        "position": 1001 + i, "caption": panel.get("caption", "")})
            chapter["ai_metadata"] = {"model": ai.get("model"), "is_test_fixture": ai.get("is_test_fixture", False)}
        else:
            chapter["summary"] = extractive_summary(chapter["title"], chapter["narrative"])
            chapter["comic_prompts"] = []
        data = {**data, "timeline": list(dict.fromkeys(data.get("timeline", []) + [f"Chapter {chapter['position']}: {chapter['title']}"[:500]]))}
        self.put(db, "story_bibles", {"id": story["id"], "version": chapter["position"], "data": data})
