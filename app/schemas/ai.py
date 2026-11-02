"""
Request and response bodies for AI help. A person's key only ever comes
in: nothing here sends one back.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.ai.evidence import FileLeft, ReviewKind
from app.ai.suggestions import CheckedSuggestion
from app.ai.vendors import AiVendor
from app.models.ai import MODEL_NAME_LENGTH, ReviewStatus

MAX_KEY_LENGTH = 512


class AiVendorView(BaseModel):
    """
    A vendor someone can choose.
    """

    id: AiVendor
    title: str
    warning: str | None = None


class SavedAiKey(BaseModel):
    """
    The key a person has saved, as far as anyone is ever shown it.
    """

    model_config = ConfigDict(from_attributes=True)

    vendor: AiVendor
    model: str
    key_ending: str = Field(
        description="Its last characters, to tell keys apart."
    )


class AiKeyState(BaseModel):
    """
    What the web app needs to offer AI help.
    """

    available: bool = Field(
        description="False if this server has no secret to keep keys with."
    )
    vendors: list[AiVendorView]
    saved: SavedAiKey | None = None


class AiKeySave(BaseModel):
    """
    A key to check with its vendor and save.
    """

    vendor: AiVendor
    key: SecretStr = Field(min_length=1, max_length=MAX_KEY_LENGTH)


class AiKeySaved(AiKeyState):
    """
    The state after saving, and the models the key can ask.
    """

    models: list[str]


class AiModelChoice(BaseModel):
    """
    The model a person's key should ask.
    """

    model: str = Field(min_length=1, max_length=MODEL_NAME_LENGTH)


class AiReadItem(BaseModel):
    """
    A file or page the model was given, and how much of it.
    """

    name: str
    shown: str


class AiReviewView(BaseModel):
    """
    One review, as the AI tab shows it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: ReviewKind
    status: ReviewStatus
    vendor: AiVendor
    model: str
    answered_by: str | None = None
    summary: str | None = None
    explanation: str | None = None
    suggestions: list[CheckedSuggestion] | None = None
    check_next: list[str] | None = None
    read_parts: list[AiReadItem] | None = None
    unread_pages: list[str] | None = None
    left_behind: list[FileLeft] | None = None
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: datetime
    finished_at: datetime | None = None


class AiReviewState(BaseModel):
    """
    What the step's window needs: what can be asked about this step, which
    its ending decides, and the newest answer. The web app shows a step
    whose parent failed as failed too, so only the server can tell them
    apart.
    """

    kind: ReviewKind | None = Field(
        default=None,
        description="What a review would do; none if it can't have one.",
    )
    review: AiReviewView | None = None
