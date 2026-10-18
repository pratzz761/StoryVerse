import json
import re
from .providers import GenerationError


def relevance_terms(idea):
    return list(dict.fromkeys(w.lower() for w in re.findall(r"\b[^\W\d_]{4,}\b", idea) if w.lower() not in {"that", "with", "this", "from", "they", "their", "about", "story", "chapter", "arrives"}))[:8]


class StoryContextBuilder:
    def __init__(self, repo, max_chars=18000):
        self.repo, self.max_chars = repo, max_chars

    async def build(self, token, story_id, idea, direction):
        snapshot = await self.repo.context_snapshot(token, story_id, relevance_terms(idea))
        story = snapshot["story"]
        data = {"premise": {"title": story["title"], "genre": story["genre"], "opening": snapshot["opening"][:1800]},
            "tone": "Continue the tone and voices of the published excerpts.", "story_version": story["version"],
            "story_bible": snapshot["bible"], "earlier_summaries": [], "recent_relevant_chapters": [],
            "contributor_idea": idea, "creative_direction": direction}
        size = lambda: len(json.dumps(data, ensure_ascii=False).encode())
        if size() > self.max_chars - 1000:
            raise GenerationError("context_limit", "The idea or Story Bible is too large. Shorten the idea or review the story's canon.", 422)
        # Recent and lexically relevant chapters are retrieved before full text is
        # loaded. Spend the context budget on recent continuity first.
        for chapter in sorted(snapshot["selected"], key=lambda c: c["position"], reverse=True):
            available = self.max_chars - size() - 300
            if available < 400:
                break
            data["recent_relevant_chapters"].append({"position": chapter["position"], "title": chapter["title"], "narrative": chapter["narrative"][:min(3000, available // 2)]})
        selected = {c["position"] for c in data["recent_relevant_chapters"]}
        # Stored structured summaries are sufficient for older chapters. Keep
        # chronological bookends if a very long outline exceeds the budget.
        outlines = [c for c in snapshot["outline"] if c["position"] not in selected]
        outlines = outlines[:10] + outlines[10:][-70:]
        for chapter in outlines:
            synopsis = chapter.get("summary", {}).get("synopsis", chapter["title"])
            entry = {"position": chapter["position"], "title": chapter["title"], "synopsis": synopsis[:240], "source": chapter.get("summary", {}).get("source", "ai")}
            data["earlier_summaries"].append(entry)
            if size() > self.max_chars:
                data["earlier_summaries"].pop()
                break
        data["omitted_outline_count"] = len(snapshot["outline"]) - len(selected) - len(data["earlier_summaries"])
        while size() > self.max_chars and data["earlier_summaries"]:
            data["earlier_summaries"].pop()
            data["omitted_outline_count"] += 1
        if size() > self.max_chars:
            raise GenerationError("context_limit", "The story context exceeds the configured limit.", 422)
        return data
