"""Isolated, disposable API database for Playwright; never touches demo user data."""
from tempfile import TemporaryDirectory
from pathlib import Path
import uvicorn
from app.config import Settings
from app.main import create_app
from app.ai.providers import GenerationError
from tests.test_ai_workflow import FixtureProvider
from tests.test_sdxl import FixtureSDXL
import asyncio


class BrowserFixtureProvider(FixtureProvider):
    def __init__(self):
        super().__init__()
        self.failed_ideas = set()

    async def structured(self, task, data, schema):
        await asyncio.sleep(.25)
        idea = data.get("contributor_idea", "")
        if idea.startswith("TEST_QUOTA_ONCE") and idea not in self.failed_ideas:
            self.failed_ideas.add(idea)
            raise GenerationError("provider_quota", "Mocked Gemini quota reached. Your draft is safe; retry shortly.", 429, 1)
        return await super().structured(task, data, schema)

if __name__ == "__main__":
    with TemporaryDirectory(prefix="storyverse-e2e-") as directory:
        # Browser journeys share one demo persona. Quotas have dedicated API/SQL
        # tests; bypass the minute cap only in this disposable fixture server.
        settings = Settings(app_mode="demo", data_dir=Path(directory), ai_mode="gemini", gemini_api_key="test-fixture-no-network",
            gemini_free_tier_confirmed=True, sdxl_enabled=True, ai_user_daily_limit=100, _env_file=None).model_copy(update={"ai_requests_per_minute":100})
        app = create_app(settings, BrowserFixtureProvider(), FixtureSDXL())
        async def discovery_fixtures():
            from app.seed import DEMO_USER
            # Isolated pagination fixtures sort after the six curated samples.
            for index in range(18):
                result = await app.state.repo.create_story(None, DEMO_USER, {"title": f"Pagination fixture {index+1:02d}",
                    "genre": "Horror", "narrative": "Hand-written browser fixture: a quiet house waits at the end of the lane.", "upload_ids": []})
                with app.state.repo.db() as db:
                    story = app.state.repo.get(db, "stories", result["id"])
                    app.state.repo.put(db, "stories", {**story, "created_at": "2010-01-01T00:00:00+00:00", "updated_at": "2010-01-01T00:00:00+00:00"})
        asyncio.run(discovery_fixtures())
        uvicorn.run(app, host="127.0.0.1", port=8001)
