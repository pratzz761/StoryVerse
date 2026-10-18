from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Genre = Literal["Fantasy", "Sci-Fi", "Mystery", "Adventure", "Romance", "Horror", "Slice of Life"]
Direction = Literal["Keep it going", "Add a twist", "Build the world", "Meet someone new"]


class WithUploads(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_ids: list[UUID] = Field(default_factory=list, max_length=6)

    @field_validator("upload_ids")
    @classmethod
    def unique_uploads(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Each attachment can only be included once")
        return values


class StoryCreate(WithUploads):
    title: str = Field(min_length=1, max_length=100)
    genre: Genre
    narrative: str = Field(min_length=1, max_length=12000)

    @field_validator("title", "narrative")
    @classmethod
    def non_blank(cls, value):
        if not value.strip():
            raise ValueError("This field cannot be blank")
        return value.strip()


class ContributionCreate(WithUploads):
    text: str = Field(default="", max_length=12000)
    direction: Direction = "Keep it going"
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def has_content(self):
        if not self.text.strip() and not self.upload_ids:
            raise ValueError("Add text or at least one attachment")
        return self


class DraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    narrative: str = Field(max_length=12000)

    @field_validator("title")
    @classmethod
    def non_blank(cls, value):
        if not value.strip():
            raise ValueError("Title cannot be blank")
        return value.strip()


class PublishRequest(BaseModel):
    expected_version: int = Field(ge=1)
    approved: Literal[True]


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_revision: int = Field(ge=0)
    consent: Literal[True]


class ContentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["spam", "harassment", "sexual_content", "violence", "privacy", "copyright", "other"]
    details: str = Field(default="", max_length=1000)


class ModerationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hidden: bool
    reason: str = Field(min_length=5, max_length=500)


class InteractionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["like", "bookmark", "follow"]
    active: bool


class ReadingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_id: UUID
    completed: bool = False
    layout: Literal["webtoon", "comic"] = "webtoon"


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=50)
    bio: str = Field(default="", max_length=300)

    @field_validator("display_name")
    @classmethod
    def non_blank(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()
