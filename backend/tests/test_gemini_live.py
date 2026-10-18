"""Opt-in live unpaid Gemini call. Never runs from credentials alone."""
import asyncio
import os
import pytest
from app.config import Settings
from app.ai.providers import GeminiProvider
from app.ai.schemas import GeneratedChapter


@pytest.mark.skipif(os.getenv("STORYVERSE_LIVE_GEMINI_TESTS") != "1", reason="Live Gemini call requires explicit opt-in, credentials and confirmed unpaid project")
def test_live_gemini_structured_chapter():
    settings = Settings()
    assert settings.ai_mode == "gemini" and settings.gemini_api_key and settings.gemini_free_tier_confirmed
    provider = GeminiProvider(settings)
    async def run():
        try:
            return await provider.structured("continue_story", {
                "premise": {"title": "The river key", "genre": "Fantasy", "opening": "Elara, a quiet village herbalist, found her mother's brass key beside the river."},
                "story_bible": {"characters": [{"name": "Elara", "description": "A quiet village herbalist.", "relationships": []}]},
                "contributor_idea": "A traveler in a grey coat warns Elara that the river will flood before dawn.",
                "creative_direction": "Add a twist"}, GeneratedChapter)
        finally:
            await provider.close()
    result = asyncio.run(run())
    assert len(result.value.panels) in (2,3,4)
    assert result.value.narrative.strip() and result.value.memory.summary.synopsis
    assert result.model == settings.gemini_model
