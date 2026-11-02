"""
Request and response bodies for AI help. A person's key only ever comes
in: nothing here sends one back.
"""

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.ai.vendors import AiVendor
from app.models.ai import MODEL_NAME_LENGTH

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
