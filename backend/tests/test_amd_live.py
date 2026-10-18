"""One real AMD chapter, opt-in only; never falls back to Gemini."""
import asyncio
import os
import pytest
from app.config import Settings
from app.ai.amd import AMDProvider
from app.ai.schemas import GeneratedChapter, merge_bible


@pytest.mark.skipif(os.getenv("STORYVERSE_LIVE_AMD_TESTS") != "1", reason="Live AMD chapter needs explicit opt-in and privately configured AMD_API_KEY")
def test_live_amd_structured_chapter():
    settings = Settings()
    ready = settings.ai_mode == "amd" and bool(settings.amd_api_key)
    assert ready, "Select AI_MODE=amd and configure AMD_API_KEY privately (values redacted)"
    provider = AMDProvider(settings)
    bible = {"characters": [{"name":"Elara", "description":"A quiet village herbalist.", "relationships":[], "personality_traits":["Observant"], "visual_description":"Dark braided hair and a green cloak."}]}
    async def run():
        try:
            return await provider.structured("continue_story", {
                "premise": {"title": "The river key", "genre": "Fantasy", "opening": "Elara, a quiet village herbalist, found her mother's brass key beside the river."},
                "story_bible": bible,
                "contributor_idea": "A traveler in a grey coat warns Elara that the river will flood before dawn.",
                "creative_direction": "Add a twist"}, GeneratedChapter)
        finally:
            await provider.close()
    result = asyncio.run(run())
    assert 2 <= len(result.value.panels) <= 4
    assert result.value.narrative.strip() and result.value.memory.summary.synopsis
    assert result.model == settings.amd_model
    merge_bible(bible, result.value.memory.additions)
