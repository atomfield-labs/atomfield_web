"""
Request and response bodies for pairing an agent with a short code.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.targets import TargetKind


class PairingRequest(BaseModel):
    """
    An agent asking to be paired, and what it says about its machine
    (shown to the person, so they can tell it is theirs).
    """

    hostname: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=100)
    kind: TargetKind = "slurm"


class PairingStarted(BaseModel):
    """
    What the agent needs to finish pairing: the code to show, the
    secret to collect its token with, and how often to ask.
    """

    code: str
    secret: str
    approve_url: str | None = None
    expires_in: int
    interval: int


class PairingPoll(BaseModel):
    """
    The agent asking whether its code was approved.
    """

    secret: str = Field(min_length=1, max_length=200)


class PairingView(BaseModel):
    """
    A pairing as the person approving it sees it.
    """

    model_config = ConfigDict(from_attributes=True)

    code: str
    hostname: str
    username: str
    address: str
    kind: str
    requested_at: datetime


class PairingApproval(BaseModel):
    """
    The person approving a pairing, naming the new cluster.
    """

    name: str = Field(min_length=1, max_length=100)
