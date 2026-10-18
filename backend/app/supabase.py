"""Supabase REST adapter. User data uses caller JWTs; AI job writes use server RPCs."""
import logging
import httpx
from fastapi import HTTPException
from .ai.supabase_store import SupabaseAIMixin
from .community import SupabaseCommunityMixin

log = logging.getLogger(__name__)


class SupabaseRepository(SupabaseAIMixin, SupabaseCommunityMixin):
    def __init__(self, settings):
        self.settings = settings
        self.client = httpx.AsyncClient(base_url=settings.supabase_url.rstrip("/"), timeout=30)

    def headers(self, token):
        # New publishable/secret keys belong in apikey, never Bearer. Ordinary
        # authenticated requests still use a user JWT with the PUBLIC key.
        if token and token == self.settings.supabase_service_role_key and token.startswith('sb_secret_'):
            return {'apikey':token}
        public_key = self.settings.supabase_anon_key
        headers = {'apikey':public_key}
        if token:
            headers['Authorization'] = 'Bearer '+token
        elif not public_key.startswith('sb_publishable_'):
            headers['Authorization'] = 'Bearer '+public_key
        return headers

    async def call(self, method, path, token, *, params=None, json=None, content=None, headers=None):
        try:
            response = await self.client.request(method, path, params=params, json=json, content=content,
                headers={**self.headers(token), **(headers or {})})
        except httpx.RequestError as exc:
            raise HTTPException(503, "Supabase is unavailable. Please try again.") from exc
        if response.is_error:
            try:
                error = response.json()
            except ValueError:
                error = {}
            code = error.get("code")
            if code == "P0001" and error.get("message") == "AI_QUOTA":
                raise HTTPException(429, "The application generation quota is reached. Your saved draft is safe.", headers={"Retry-After": "60"})
            if code == "P0001" and error.get("message") == "WRITE_QUOTA":
                raise HTTPException(429, "The writing or upload limit is reached. Please retry later.", headers={"Retry-After":"60"})
            if code == "P0001" and error.get("message") == "AI_BUSY":
                raise HTTPException(409, "A generation is already in progress. Your saved draft is safe.")
            if code in ("40001", "23505"):
                raise HTTPException(409, "The story changed or this draft is already published. Read the latest chapter and create a new draft.")
            if response.status_code == 401 or code in ("PGRST301", "PGRST303"):
                raise HTTPException(401, "Your session expired. Please sign in again.")
            if code == "P0002":
                raise HTTPException(404, "Not found")
            if code == "42501" or response.status_code == 403:
                raise HTTPException(403, "You do not have permission for this action")
            if code in ("22023", "23514"):
                raise HTTPException(422, "Check your chapter text and attachment ownership")
            log.warning("Supabase request failed: status=%s code=%s path=%s", response.status_code, code, path.split("?")[0])
            raise HTTPException(502, "The storage or database request failed. Check the migrations and Supabase configuration.")
        return response

    async def rest(self, table, token, params=None, method="GET", values=None):
        response = await self.call(method, f"/rest/v1/{table}", token, params=params, json=values,
            headers={"Prefer": "return=representation"})
        return response.json() if response.content else None

    async def rpc(self, name, token, values):
        return await self.rest(f"rpc/{name}", token, method="POST", values=values)

    async def authenticate(self, token):
        response = await self.call("GET", "/auth/v1/user", token)
        user = response.json()
        if not user.get("id"):
            raise HTTPException(401, "Invalid session")
        if self.settings.app_environment == "production" and not user.get("email_confirmed_at"):
            raise HTTPException(403, "Confirm your email before using this account")
        return user["id"]

    async def save_worker_upload(self, owner, job_id, content):
        key = self.settings.supabase_service_role_key
        existing = await self.rest('uploads', key, {'id':f'eq.{job_id}', 'owner_id':f'eq.{owner}'})
        if existing:
            import hashlib
            saved = await self.read_upload(key, existing[0])
            if hashlib.sha256(saved).digest() != hashlib.sha256(content).digest():
                raise HTTPException(409, 'Worker retry returned different image bytes')
            return existing[0]
        return await self.save_upload(key, owner, job_id, 'sdxl-panel.png', 'image/png', content, None)

    async def profile(self, token, user_id):
        rows = await self.rest("profiles", token, {"id": f"eq.{user_id}", "select": "*"})
        if not rows:
            raise HTTPException(404, "Profile not found")
        return rows[0]

    async def update_profile(self, token, user_id, values):
        rows = await self.rest("profiles", token, {"id": f"eq.{user_id}"}, "PATCH", values)
        if not rows:
            raise HTTPException(404, "Profile not found")
        return rows[0]

    async def hydrate_stories(self, token, stories):
        if not stories:
            return []
        ids = ",".join(s["id"] for s in stories)
        chapters = await self.rest("chapters", token, {"story_id": f"in.({ids})", "select": "story_id,author_id"})
        profiles = await self.rest("profiles", token, {"id": f"in.({','.join(set(s['owner_id'] for s in stories))})"})
        owners = {p["id"]: p for p in profiles}
        engagement = []
        for start in range(0, len(stories), 60):
            engagement.extend(await self.rpc("story_engagement", token, {"p_story_ids": [s["id"] for s in stories[start:start+60]]}))
        counts = {e["story_id"]: e for e in engagement}
        for s in stories:
            related = [c for c in chapters if c["story_id"] == s["id"]]
            s.update(chapter_count=len(related), contributor_count=len({c["author_id"] for c in related}), owner=owners.get(s["owner_id"]))
            s.update({k: counts[s["id"]][k] for k in ("like_count", "bookmark_count", "follow_count")})
            s["cover_url"] = f"/api/uploads/{s['cover_upload_id']}/file" if s.get("cover_upload_id") else f"/covers/{s['cover_art']}.svg"
        return stories

    async def list_stories(self, token, search="", genre=None, sort="trending"):
        return (await self.discover(token, search, genre, sort, 1, 60))["items"]

    async def attachments(self, token, ids):
        if not ids:
            return []
        rows = await self.rest("uploads", token, {"id": f"in.({','.join(ids)})"})
        # URLs are access-checked by the API, never permanent public Storage URLs.
        by_id = {x["id"]: x for x in rows}
        return [{**by_id[object_id], "url": f"/api/uploads/{object_id}/file"} for object_id in ids if object_id in by_id]

    async def story(self, token, story_id):
        rows = await self.rest("stories", token, {"id": f"eq.{story_id}"})
        if not rows:
            raise HTTPException(404, "Story not found")
        story = (await self.hydrate_stories(token, rows))[0]
        chapters = await self.rest("chapters", token, {"story_id": f"eq.{story_id}", "order": "position.asc", "select": "*,author:profiles!chapters_author_id_fkey(*)"})
        for c in chapters:
            c["attachments"] = await self.attachments(token, c["upload_ids"])
            c["panels"] = [{"id": a["id"], "image_url": a["url"], "caption": a["filename"]} for a in c["attachments"] if a["mime_type"].startswith("image/")]
        return {**story, "chapters": chapters}

    async def user_stories(self, token, user_id):
        created = await self.rest("stories", token, {"owner_id": f"eq.{user_id}", "order": "created_at.desc"})
        chapters = await self.rest("chapters", token, {"author_id": f"eq.{user_id}", "select": "story_id"})
        ids = ",".join(set(c["story_id"] for c in chapters))
        contributed = await self.rest("stories", token, {"id": f"in.({ids})", "order": "updated_at.desc"}) if ids else []
        result = {"created": await self.hydrate_stories(token, created), "contributed": await self.hydrate_stories(token, contributed)}
        actions = await self.rest("story_interactions", token, {"user_id": f"eq.{user_id}", "select": "story_id,kind"})
        for key, kind in (("bookmarked", "bookmark"), ("followed", "follow")):
            selected = ",".join(a["story_id"] for a in actions if a["kind"] == kind)
            rows = await self.rest("stories", token, {"id": f"in.({selected})", "order": "updated_at.desc,id.asc"}) if selected else []
            result[key] = await self.hydrate_stories(token, rows)
        progress = await self.rest("reading_progress", token, {"user_id": f"eq.{user_id}", "order": "updated_at.desc"})
        ids = ",".join(p["story_id"] for p in progress)
        reading = await self.hydrate_stories(token, await self.rest("stories", token, {"id": f"in.({ids})"})) if ids else []
        by_id = {s["id"]: s for s in reading}
        result["reading"] = [{**by_id[p["story_id"]], "reading_progress": p} for p in progress if p["story_id"] in by_id]
        return result

    async def create_story(self, token, user_id, values):
        result = await self.rpc("create_story", token, {"p_title": values["title"], "p_genre": values["genre"], "p_narrative": values["narrative"], "p_upload_ids": values["upload_ids"]})
        return {"id": result}

    async def create_contribution(self, token, user_id, story_id, values):
        result = await self.rpc("create_contribution_preview", token, {"p_story_id": str(story_id), "p_text": values["text"],
            "p_direction": values["direction"], "p_expected_version": values["expected_version"], "p_upload_ids": values["upload_ids"]})
        return {"id": result}

    async def list_drafts(self, token, user_id):
        rows = await self.rest("drafts", token, {"owner_id": f"eq.{user_id}", "status": "eq.draft", "order": "created_at.desc", "select": "*,story:stories(title)"})
        return [{**d, "story_title": d.pop("story")["title"]} for d in rows]

    async def draft(self, token, user_id, draft_id):
        rows = await self.rest("drafts", token, {"id": f"eq.{draft_id}", "owner_id": f"eq.{user_id}"})
        if not rows:
            raise HTTPException(404, "Draft not found")
        d = rows[0]
        jobs = await self.rest("generation_jobs", token, {"draft_id": f"eq.{draft_id}", "order": "created_at.desc", "limit": "20", "select": "id,status,error_code,kind"})
        text_job = next((j for j in jobs if j["kind"] != "image"), {})
        image_job = next((j for j in jobs if j["kind"] == "image"), {})
        d["generation_error"] = text_job.get("error_code") if text_job.get("status") == "failed" else None
        d["image_generation_error"] = image_job.get("error_code") if image_job.get("status") == "failed" else None
        d["pending_image_job"] = image_job.get("id") if image_job.get("status") == "running" and self.settings.sdxl_execution == "worker" else None
        stories = await self.rest("stories", token, {"id": f"eq.{d['story_id']}"})
        if not stories:
            raise HTTPException(404, "This story is unavailable")
        return {**d, "attachments": await self.attachments(token, d["upload_ids"]), "story": (await self.hydrate_stories(token, stories))[0]}

    async def update_draft(self, token, user_id, draft_id, values):
        rows = await self.rest("drafts", token, {"id": f"eq.{draft_id}", "owner_id": f"eq.{user_id}", "status": "eq.draft"}, "PATCH", values)
        if not rows:
            raise HTTPException(409, "Draft is missing or already published")
        return {"id": rows[0]["id"]}

    async def regenerate(self, token, user_id, draft_id):
        await self.rpc("reset_demo_preview", token, {"p_draft_id": str(draft_id)})
        return await self.draft(token, user_id, draft_id)

    async def publish(self, token, user_id, draft_id, expected_version):
        return await self.rpc("publish_chapter", token, {"p_draft_id": str(draft_id), "p_expected_version": expected_version, "p_approved": True})

    async def save_upload(self, token, user_id, upload_id, filename, mime_type, content, data_dir):
        path = f"{user_id}/{upload_id}"
        await self.call("POST", f"/storage/v1/object/story-media/{path}", token, content=content, headers={"Content-Type": mime_type, "x-upsert": "false"})
        item = {"id": upload_id, "owner_id": user_id, "filename": filename, "mime_type": mime_type, "size_bytes": len(content), "storage_path": path}
        try:
            rows = await self.rest("uploads", token, method="POST", values=item)
        except Exception:
            # A failed metadata write must not leave an inaccessible orphan object.
            await self.call("DELETE", "/storage/v1/object/story-media", token, json={"prefixes": [path]})
            raise
        return {**rows[0], "url": f"/api/uploads/{upload_id}/file"}

    async def get_upload(self, token, user_id, upload_id):
        rows = await self.rest("uploads", token, {"id": f"eq.{upload_id}"})
        if not rows:
            raise HTTPException(404, "File not found")
        return rows[0]

    async def read_upload(self, token, item):
        response = await self.call("GET", f"/storage/v1/object/authenticated/story-media/{item['storage_path']}", token)
        return response.content
