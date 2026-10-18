"""Explicit opt-in GPU inference; no Gemini call and never enabled by credentials alone."""
import asyncio
import os
import pytest
from app.config import Settings
from app.ai.sdxl import LocalSDXLProvider, validate_png


@pytest.mark.skipif(os.getenv("STORYVERSE_LIVE_SDXL_TESTS") != "1", reason="Local SDXL runtime and explicit live-inference opt-in required")
def test_live_local_sdxl_panel():
    settings = Settings()
    assert settings.sdxl_enabled, "Enable SDXL and start the configured local runtime first"
    provider = LocalSDXLProvider(settings)
    async def run():
        try:
            return await provider.generate({"description":"A lone traveler in a grey coat stands on a wooden bridge at dawn.",
                "location":"A woodland river", "characters":[], "camera":"Wide establishing shot", "caption":""}, {"bible":{},"seed":settings.sdxl_seed})
        finally:
            await provider.close()
    result = asyncio.run(run())
    assert validate_png(result.content, settings.sdxl_width, settings.sdxl_height)
    assert result.metadata["provider"] == "local_sdxl" and not result.metadata["is_test_fixture"]
