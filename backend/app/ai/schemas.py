import hashlib
import json
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Structured(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Character(Structured):
    name: Name
    description: Short
    relationships: list[Short] = Field(default_factory=list, max_length=12)
    personality_traits: list[Short] = Field(default_factory=list, max_length=12)
    visual_description: str = Field(default="", max_length=500)


class Location(Structured):
    name: Name
    description: Short


class StoryBible(Structured):
    characters: list[Character] = Field(default_factory=list, max_length=64)
    locations: list[Location] = Field(default_factory=list, max_length=64)
    world_rules: list[Short] = Field(default_factory=list, max_length=100)
    timeline: list[Short] = Field(default_factory=list, max_length=300)
    important_events: list[Short] = Field(default_factory=list, max_length=150)
    unresolved_plotlines: list[Short] = Field(default_factory=list, max_length=100)
    resolved_plotlines: list[Short] = Field(default_factory=list, max_length=100)


class CanonAdditions(Structured):
    characters: list[Character] = Field(default_factory=list, max_length=8)
    locations: list[Location] = Field(default_factory=list, max_length=8)
    world_rules: list[Short] = Field(default_factory=list, max_length=8)
    important_events: list[Short] = Field(default_factory=list, max_length=8)
    unresolved_plotlines: list[Short] = Field(default_factory=list, max_length=8)
    resolved_plotlines: list[Short] = Field(default_factory=list, max_length=8)


class ChapterSummary(Structured):
    synopsis: str = Field(min_length=1, max_length=1200)
    events: list[Short] = Field(default_factory=list, max_length=8)
    characters: list[Name] = Field(default_factory=list, max_length=12)
    unresolved_plotlines: list[Short] = Field(default_factory=list, max_length=8)


class MemoryOutput(Structured):
    summary: ChapterSummary
    additions: CanonAdditions


class Dialogue(Structured):
    speaker: Name
    text: Short


class Scene(Structured):
    location: Name
    description: Short
    characters: list[Name] = Field(default_factory=list, max_length=8)


class ComicPrompt(Structured):
    description: str = Field(min_length=20, max_length=1200)
    characters: list[Name] = Field(default_factory=list, max_length=8)
    location: Name
    camera: str = Field(min_length=1, max_length=160)
    caption: str = Field(default="", max_length=300)


class GeneratedChapter(Structured):
    title: str = Field(min_length=1, max_length=100)
    narrative: str = Field(min_length=80, max_length=12000)
    dialogue: list[Dialogue] = Field(default_factory=list, max_length=12)
    scenes: list[Scene] = Field(min_length=1, max_length=5)
    panels: list[ComicPrompt] = Field(min_length=2, max_length=4)
    memory: MemoryOutput

    @model_validator(mode="after")
    def nonblank(self):
        if not self.title.strip() or not self.narrative.strip():
            raise ValueError("A chapter needs a title and narrative")
        return self


def narrative_hash(title, narrative):
    return hashlib.sha256(json.dumps([title, narrative], ensure_ascii=False).encode()).hexdigest()


def extractive_summary(title, narrative):
    return {"synopsis": narrative.strip()[:600] or title, "events": [], "characters": [], "unresolved_plotlines": [], "source": "extractive"}


def merge_bible(existing: dict, additions: CanonAdditions) -> dict:
    """Append facts; a provider cannot silently rewrite a canonical description."""
    bible = StoryBible.model_validate(existing or {}).model_dump()
    delta = additions.model_dump()
    for category in ("characters", "locations"):
        known = {x["name"].casefold(): x for x in bible[category]}
        for item in delta.pop(category):
            old = known.get(item["name"].casefold())
            if old:
                if old["description"] != item["description"]:
                    raise ValueError(f"Conflicting established {category} description")
                if category == "characters":
                    old["relationships"] = list(dict.fromkeys(old["relationships"] + item["relationships"]))
                    if old["visual_description"] and item["visual_description"] and old["visual_description"] != item["visual_description"]:
                        raise ValueError("Conflicting established character visual description")
                    if item["visual_description"]:
                        old["visual_description"] = item["visual_description"]
                    old["personality_traits"] = list(dict.fromkeys(old["personality_traits"] + item["personality_traits"]))
            else:
                bible[category].append(item)
                known[item["name"].casefold()] = item
    if any(p not in bible["unresolved_plotlines"] for p in delta["resolved_plotlines"]):
        raise ValueError("Only an established plotline can be marked resolved")
    for category, items in delta.items():
        bible[category] = list(dict.fromkeys(bible[category] + items))
    validated = StoryBible.model_validate(bible).model_dump()
    if len(json.dumps(validated, ensure_ascii=False).encode()) > 14000:
        raise ValueError("Story Bible capacity reached; review canon before continuing")
    return validated
