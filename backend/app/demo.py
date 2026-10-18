import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from fastapi import HTTPException
from .seed import DEMO_USER, PROFILES, SAMPLES, FOREST_BIBLE
from .ai.local_store import LocalAIMixin
from .ai.schemas import StoryBible, extractive_summary
from .community import LocalCommunityMixin


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


class DemoRepository(LocalAIMixin, LocalCommunityMixin):
    """Durable local demo, with the same version contract as PostgreSQL."""

    def __init__(self, data_dir):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "storyverse.sqlite3"
        with self.db() as db:
            for name in ("profiles", "stories", "chapters", "contributions", "drafts", "panels", "uploads", "story_interactions", "reading_progress"):
                db.execute(f"CREATE TABLE IF NOT EXISTS {name} (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            if not db.execute("SELECT 1 FROM profiles LIMIT 1").fetchone():
                for p in PROFILES:
                    self.put(db, "profiles", {**p, "created_at": now()})
                for i, (title, genre, art, description, chapters) in enumerate(SAMPLES):
                    story_id = f"aaaaaaaa-aaaa-4aaa-8aaa-{i + 1:012d}"
                    stamp = (datetime.now(timezone.utc) - timedelta(days=i + 1)).isoformat()
                    self.put(db, "stories", {"id": story_id, "title": title, "genre": genre, "cover_art": art,
                        "description": description, "owner_id": PROFILES[i % 3]["id"], "version": len(chapters),
                        "is_demo": True, "cover_upload_id": None, "created_at": stamp, "updated_at": stamp})
                    for j, (chapter_title, narrative) in enumerate(chapters):
                        self.put(db, "chapters", {"id": uid(), "story_id": story_id, "position": j + 1,
                            "title": chapter_title, "narrative": narrative, "author_id": PROFILES[(i + j) % 3]["id"],
                            "source": "sample", "upload_ids": [], "created_at": stamp})

            self.initialize_ai(db)
            sample_id = "aaaaaaaa-aaaa-4aaa-8aaa-000000000001"
            sample = next((s for s in self.rows(db, "stories") if s["id"] == sample_id), None)
            if sample and sample.get("is_demo"):
                bible = self.get(db, "story_bibles", sample_id)
                # Enrich only a pristine sample Bible, never established user/AI canon.
                if not bible["data"].get("characters") and not bible["data"].get("important_events"):
                    self.put(db, "story_bibles", {**bible, "data": StoryBible.model_validate({**bible["data"], **FOREST_BIBLE}).model_dump()})

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def put(db, table, value):
        db.execute(f"INSERT OR REPLACE INTO {table}(id,data) VALUES (?,?)", (value["id"], json.dumps(value)))

    @staticmethod
    def rows(db, table):
        return [json.loads(r[0]) for r in db.execute(f"SELECT data FROM {table}")]

    @staticmethod
    def get(db, table, object_id):
        row = db.execute(f"SELECT data FROM {table} WHERE id=?", (str(object_id),)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        return json.loads(row[0])

    def media(self, db, ids):
        return [{**self.get(db, "uploads", x), "url": f"/api/uploads/{x}/file"} for x in ids]

    def owned_uploads(self, db, ids, user_id):
        for object_id in ids:
            if self.get(db, "uploads", object_id)["owner_id"] != user_id:
                raise HTTPException(403, "An attachment belongs to another user")

    def hydrate_story(self, db, story):
        chapters = [c for c in self.rows(db, "chapters") if c["story_id"] == story["id"]]
        counts = self.engagement_in(db, story["id"])
        return {**story, **{k: counts[k] for k in ("like_count", "bookmark_count", "follow_count")}, "chapter_count": len(chapters), "contributor_count": len({c["author_id"] for c in chapters}),
            "owner": self.get(db, "profiles", story["owner_id"]),
            "cover_url": f"/api/uploads/{story['cover_upload_id']}/file" if story.get("cover_upload_id") else f"/covers/{story['cover_art']}.svg"}

    def hydrate_chapter(self, db, chapter):
        attachments = self.media(db, chapter["upload_ids"])
        return {**chapter, "author": self.get(db, "profiles", chapter["author_id"]), "attachments": attachments,
            "panels": [{"id": x["id"], "image_url": x["url"], "caption": x["filename"]} for x in attachments if x["mime_type"].startswith("image/")]}

    async def list_stories(self, token, search="", genre=None, sort="trending"):
        return (await self.discover(token, search, genre, sort, 1, 60))["items"]

    async def story(self, token, story_id):
        with self.db() as db:
            story = self.hydrate_story(db, self.get(db, "stories", story_id))
            chapters = sorted([self.hydrate_chapter(db, c) for c in self.rows(db, "chapters") if c["story_id"] == str(story_id)], key=lambda c: c["position"])
            return {**story, "chapters": chapters}

    async def profile(self, token, user_id):
        with self.db() as db:
            return self.get(db, "profiles", user_id)

    async def update_profile(self, token, user_id, values):
        with self.db() as db:
            p = {**self.get(db, "profiles", user_id), **values}
            self.put(db, "profiles", p)
            return p

    async def user_stories(self, token, user_id):
        with self.db() as db:
            contributed = {c["story_id"] for c in self.rows(db, "chapters") if c["author_id"] == user_id}
            stories = [self.hydrate_story(db, s) for s in self.rows(db, "stories")]
            actions = [a for a in self.rows(db, "story_interactions") if a["user_id"] == user_id]
            progress = {r["story_id"]: r for r in self.rows(db, "reading_progress") if r["user_id"] == user_id}
            stories.sort(key=lambda s: (s["updated_at"], s["id"]), reverse=True)
            return {"created": [s for s in stories if s["owner_id"] == user_id], "contributed": [s for s in stories if s["id"] in contributed],
                "bookmarked": [s for s in stories if any(a["story_id"] == s["id"] and a["kind"] == "bookmark" for a in actions)],
                "followed": [s for s in stories if any(a["story_id"] == s["id"] and a["kind"] == "follow" for a in actions)],
                "reading": sorted([{**s, "reading_progress": progress[s["id"]]} for s in stories if s["id"] in progress],
                    key=lambda s: (s["reading_progress"]["updated_at"], s["id"]), reverse=True)}

    async def create_story(self, token, user_id, values):
        with self.db() as db:
            self.owned_uploads(db, values["upload_ids"], user_id)
            images = [x for x in self.media(db, values["upload_ids"]) if x["mime_type"].startswith("image/")]
            story = {"id": uid(), "title": values["title"], "genre": values["genre"], "owner_id": user_id,
                "description": values["narrative"][:180], "version": 1, "is_demo": False, "cover_art": "forest",
                "cover_upload_id": images[0]["id"] if images else None, "created_at": now(), "updated_at": now()}
            self.put(db, "stories", story)
            chapter_id = uid()
            self.put(db, "chapters", {"id": chapter_id, "story_id": story["id"], "position": 1, "title": "The beginning",
                "narrative": values["narrative"], "author_id": user_id, "source": "manual", "upload_ids": values["upload_ids"], "created_at": now(),
                "summary": extractive_summary("The beginning", values["narrative"]), "comic_prompts": []})
            self.put(db, "story_bibles", {"id": story["id"], "version": 1, "data": StoryBible(timeline=["Chapter 1: The beginning"]).model_dump()})
            for i, image in enumerate(images):
                self.put(db, "panels", {"id": uid(), "chapter_id": chapter_id, "upload_id": image["id"], "position": i + 1})
            self.make_public(db, values["upload_ids"])
            return {"id": story["id"]}

    def make_public(self, db, ids):
        for object_id in ids:
            self.put(db, "uploads", {**self.get(db, "uploads", object_id), "is_public": True})

    async def create_contribution(self, token, user_id, story_id, values):
        with self.db() as db:
            story = self.get(db, "stories", story_id)
            if story["version"] != values["expected_version"]:
                raise HTTPException(409, "A new chapter was published. Refresh the story before continuing.")
            self.owned_uploads(db, values["upload_ids"], user_id)
            contribution = {"id": uid(), "story_id": str(story_id), "author_id": user_id, **values, "created_at": now()}
            self.put(db, "contributions", contribution)
            draft = {"id": uid(), "story_id": str(story_id), "owner_id": user_id, "contribution_id": contribution["id"],
                "title": f"Chapter {story['version'] + 1}", "narrative": values["text"].strip(), "base_version": story["version"],
                "upload_ids": values["upload_ids"], "status": "draft", "source": "demo_preview", "created_at": now()}
            self.put(db, "drafts", draft)
            return {"id": draft["id"]}

    def owned_draft(self, db, draft_id, user_id):
        draft = self.get(db, "drafts", draft_id)
        if draft["owner_id"] != user_id:
            raise HTTPException(404, "Draft not found")
        return draft

    async def list_drafts(self, token, user_id):
        with self.db() as db:
            return [{**d, "story_title": self.get(db, "stories", d["story_id"])["title"]} for d in self.rows(db, "drafts") if d["owner_id"] == user_id and d["status"] == "draft"]

    async def draft(self, token, user_id, draft_id):
        with self.db() as db:
            d = self.owned_draft(db, draft_id, user_id)
            jobs = [j for j in self.rows(db, "generation_jobs") if j["draft_id"] == str(draft_id) and j["owner_id"] == user_id]
            text_job = max((j for j in jobs if j["kind"] != "image"), key=lambda j:j["started_at"], default={})
            image_job = max((j for j in jobs if j["kind"] == "image"), key=lambda j:j["started_at"], default={})
            return {**d, "revision": d.get("revision", 0), "generation_error": text_job.get("error_code") if text_job.get("status") == "failed" else None,
                "image_generation_error": image_job.get("error_code") if image_job.get("status") == "failed" else None,
                "attachments": self.media(db, d["upload_ids"]), "story": self.hydrate_story(db, self.get(db, "stories", d["story_id"]))}

    async def update_draft(self, token, user_id, draft_id, values):
        with self.db() as db:
            d = self.owned_draft(db, draft_id, user_id)
            if d["status"] != "draft":
                raise HTTPException(409, "This chapter is already published")
            changed = any(d[k] != v for k, v in values.items())
            self.put(db, "drafts", {**d, **values, "revision": d.get("revision", 0) + int(changed)})
            return {"id": d["id"]}

    async def regenerate(self, token, user_id, draft_id):
        with self.db() as db:
            d = self.owned_draft(db, draft_id, user_id)
            if d.get("source") == "ai_generated":
                raise HTTPException(409, "AI regeneration creates a new version. Use the generate endpoint.")
            if d["status"] != "draft":
                raise HTTPException(409, "This chapter is already published")
            c = self.get(db, "contributions", d["contribution_id"])
            title, narrative = f"Chapter {d['base_version'] + 1}", c["text"].strip()
            changed = d["title"] != title or d["narrative"] != narrative
            self.put(db, "drafts", {**d, "title": title, "narrative": narrative, "revision": d.get("revision", 0) + int(changed)})
        return await self.draft(token, user_id, draft_id)

    async def publish(self, token, user_id, draft_id, expected_version):
        with self.db() as db:
            d = self.owned_draft(db, draft_id, user_id)
            s = self.get(db, "stories", d["story_id"])
            if d["status"] == "published" and d.get("source") == "ai_generated" and d["base_version"] == expected_version:
                return d["publication"]
            if d["status"] != "draft" or s["version"] != expected_version or d["base_version"] != expected_version:
                raise HTTPException(409, "The story has changed or this chapter is already published. Read the latest chapter and create a new draft.")
            if not d["narrative"].strip():
                raise HTTPException(422, "Add a narrative before publishing")
            chapter = {"id": uid(), "story_id": s["id"], "position": s["version"] + 1, "title": d["title"],
                "narrative": d["narrative"], "author_id": user_id, "source": d.get("source", "demo_preview"), "upload_ids": d["upload_ids"], "created_at": now()}
            self.publish_memory(db, s, d, chapter)
            self.put(db, "chapters", chapter)
            for i, attachment in enumerate(self.media(db, d["upload_ids"])):
                if attachment["mime_type"].startswith("image/"):
                    self.put(db, "panels", {"id": uid(), "chapter_id": chapter["id"], "upload_id": attachment["id"], "position": i + 1})
            self.put(db, "stories", {**s, "version": s["version"] + 1, "updated_at": now()})
            self.put(db, "drafts", {**d, "status": "published", "publication": {"story_id": s["id"], "chapter_id": chapter["id"], "version": s["version"] + 1}})
            self.make_public(db, d["upload_ids"])
            return {"story_id": s["id"], "chapter_id": chapter["id"], "version": s["version"] + 1}

    async def save_upload(self, token, user_id, upload_id, filename, mime_type, content, data_dir):
        path = data_dir / "uploads" / upload_id
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        with self.db() as db:
            item = {"id": upload_id, "owner_id": user_id, "filename": filename, "mime_type": mime_type,
                "size_bytes": len(content), "is_public": False, "created_at": now()}
            self.put(db, "uploads", item)
        return {**item, "url": f"/api/uploads/{upload_id}/file"}

    async def get_upload(self, token, user_id, upload_id):
        with self.db() as db:
            item = self.get(db, "uploads", upload_id)
            if not item["is_public"] and item["owner_id"] != user_id:
                raise HTTPException(404, "File not found")
            return item
