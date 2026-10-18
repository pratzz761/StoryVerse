"""Persisted community actions, deterministic discovery and private reading cursors."""
from datetime import datetime, timezone
import json
from fastapi import HTTPException


class LocalCommunityMixin:
    def engagement_in(self, db, story_id, user_id=None):
        self.get(db, "stories", story_id)
        rows = [r for r in self.rows(db, "story_interactions") if r["story_id"] == story_id]
        return {"story_id": story_id, **{f"{kind}_count": sum(r["kind"] == kind for r in rows) for kind in ("like", "bookmark", "follow")},
            **{kind: any(r["kind"] == kind and r["user_id"] == user_id for r in rows) for kind in ("like", "bookmark", "follow")}}

    async def engagement(self, token, user_id, story_id):
        with self.db() as db:
            return self.engagement_in(db, story_id, user_id)

    async def set_interaction(self, token, user_id, story_id, kind, active):
        with self.db() as db:
            self.get(db, "profiles", user_id)
            self.get(db, "stories", story_id)
            key = f"{user_id}:{story_id}:{kind}"
            if active:
                db.execute("INSERT OR IGNORE INTO story_interactions(id,data) VALUES (?,?)", (key, json.dumps({
                    "id": key, "user_id": user_id, "story_id": story_id, "kind": kind, "created_at": datetime.now(timezone.utc).isoformat()})))
            else:
                db.execute("DELETE FROM story_interactions WHERE id=?", (key,))
            return self.engagement_in(db, story_id, user_id)

    async def discover(self, token, search="", genre=None, sort="trending", page=1, page_size=12):
        with self.db() as db:
            stories = [self.hydrate_story(db, s) for s in self.rows(db, "stories")
                if (not genre or s["genre"] == genre) and search.casefold() in (s["title"] + " " + s["description"]).casefold()]
        # Stable ID tie-break; no synthetic scores or randomness.
        stories.sort(key=lambda s: s["id"])
        stories.sort(key=lambda s: (s["like_count"], s["follow_count"], s["chapter_count"], s["updated_at"])
            if sort == "trending" else (s["updated_at"],), reverse=True)
        start = (page - 1) * page_size
        return {"items": stories[start:start + page_size], "total": len(stories), "page": page, "page_size": page_size,
            "has_next": start + page_size < len(stories)}

    async def reading_progress(self, token, user_id, story_id):
        with self.db() as db:
            self.get(db, "stories", story_id)
            row = db.execute("SELECT data FROM reading_progress WHERE id=?", (f"{user_id}:{story_id}",)).fetchone()
            return json.loads(row[0]) if row else None

    async def save_reading_progress(self, token, user_id, story_id, values):
        with self.db() as db:
            self.get(db, "profiles", user_id)
            chapter = self.get(db, "chapters", values["chapter_id"])
            if chapter["story_id"] != story_id:
                raise HTTPException(422, "The chapter does not belong to this story")
            key = f"{user_id}:{story_id}"
            old = next((r for r in self.rows(db, "reading_progress") if r["id"] == key), {})
            result = {"id": key, "user_id": user_id, "story_id": story_id, "chapter_id": chapter["id"], "position": chapter["position"],
                "completed_position": max(old.get("completed_position", 0), chapter["position"] if values["completed"] else 0),
                "layout": values["layout"]}
            unchanged = old and all(old.get(k) == v for k, v in result.items())
            result["updated_at"] = old["updated_at"] if unchanged else datetime.now(timezone.utc).isoformat()
            self.put(db, "reading_progress", result)
            return result

    async def story_bible(self, token, story_id):
        from .ai.schemas import StoryBible
        with self.db() as db:
            story = self.get(db, "stories", story_id)
            row = self.get(db, "story_bibles", story_id)
            return {"story_id": story_id, "version": story["version"], "data": StoryBible.model_validate(row["data"]).model_dump()}


class SupabaseCommunityMixin:
    async def engagement(self, token, user_id, story_id):
        rows = await self.rpc("story_engagement", token, {"p_story_ids": [story_id]})
        if not rows:
            raise HTTPException(404, "Story not found")
        return rows[0]

    async def set_interaction(self, token, user_id, story_id, kind, active):
        return await self.rpc("set_story_interaction", token, {"p_story_id": story_id, "p_kind": kind, "p_active": active})

    async def discover(self, token, search="", genre=None, sort="trending", page=1, page_size=12):
        result = await self.rpc("discover_stories", token, {"p_search": search, "p_genre": genre, "p_sort": sort, "p_page": page, "p_page_size": page_size})
        result["items"] = await self.hydrate_stories(token, result["items"])
        return result

    async def reading_progress(self, token, user_id, story_id):
        if not await self.rest("stories", token, {"id": f"eq.{story_id}", "select": "id"}):
            raise HTTPException(404, "Story not found")
        rows = await self.rest("reading_progress", token, {"story_id": f"eq.{story_id}", "user_id": f"eq.{user_id}"})
        return rows[0] if rows else None

    async def save_reading_progress(self, token, user_id, story_id, values):
        return await self.rpc("save_reading_progress", token, {"p_story_id": story_id, "p_chapter_id": values["chapter_id"],
            "p_completed": values["completed"], "p_layout": values["layout"]})

    async def story_bible(self, token, story_id):
        from .ai.schemas import StoryBible
        rows = await self.rest("story_bibles", token, {"story_id": f"eq.{story_id}"})
        if not rows:
            raise HTTPException(404, "Story Bible not found")
        return {**rows[0], "data": StoryBible.model_validate(rows[0]["data"]).model_dump()}
