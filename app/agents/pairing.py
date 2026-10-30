"""
Pairing an agent with a short code, so nobody copies a token. The
agent asks for a pairing and shows its code; the person, signed in,
approves the code in the web app; the agent, which alone holds the
pairing's secret, then collects its token.

Pairings live in Redis for minutes, like sign-ins in progress; the
compute target they become is the record, in Postgres.
"""

import hmac
import json
import secrets
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.core.security import hash_api_key
from app.schemas.pairings import PairingRequest

# Consonants only: no code spells a word, and none look alike.
CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"
CODE_LENGTH = 8
# Codes are shown as two groups of four: QKTW-MZRB.
CODE_GROUP = 4
PAIRING_SECONDS = 600
# How often the agent asks whether the code was approved.
POLL_SECONDS = 5
SECRET_BYTES = 32
PAIRING_KEY = "pairing:{code}"
# Taken by the first approval of a code, so a second one changes
# nothing.
APPROVAL_KEY = "pairing-approval:{code}"
# A fresh code clashing with one in use is a one in 10^10 event.
CODE_TRIES = 3


def new_code() -> str:
    """
    A fresh, unguessable code.

    :return: Eight letters, e.g. ``QKTWMZRB``.
    :rtype: str
    """
    letters = (secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return "".join(letters)


def normalize_code(text: str) -> str:
    """
    A code as typed, with case, spaces and dashes forgiven.

    :param text: What the person typed, e.g. ``qktw-mzrb``.
    :type text: str
    :return: The code, e.g. ``QKTWMZRB``.
    :rtype: str
    """
    return "".join(letter for letter in text.upper() if letter in CODE_ALPHABET)


def shown_code(code: str) -> str:
    """
    A code as people read it.

    :param code: The code.
    :type code: str
    :return: Two groups of four, e.g. ``QKTW-MZRB``.
    :rtype: str
    """
    return f"{code[:CODE_GROUP]}-{code[CODE_GROUP:]}"


@dataclass(frozen=True, slots=True)
class Pairing:
    """
    One agent asking to be paired.

    :param code: What the person types to approve it.
    :type code: str
    :param secret_hash: Hash of the secret only the asking agent holds.
    :type secret_hash: str
    :param hostname: The machine's name, as its agent reports it.
    :type hostname: str
    :param username: Who runs the agent there.
    :type username: str
    :param address: Where the request came from, as the server saw it.
    :type address: str
    :param kind: How the machine runs jobs (``slurm`` or ``local``).
    :type kind: str
    :param requested_at: When the agent asked (ISO 8601, UTC).
    :type requested_at: str
    :param owner_id: Who approved it; None until then.
    :type owner_id: str | None
    :param target_id: The compute target it became; None until then.
    :type target_id: str | None
    """

    code: str
    secret_hash: str
    hostname: str
    username: str
    address: str
    kind: str
    requested_at: str
    owner_id: str | None = None
    target_id: str | None = None

    @property
    def approved(self) -> bool:
        """
        Whether a person has approved it.

        :return: True once approved.
        :rtype: bool
        """
        return self.target_id is not None

    def asked_by(self, secret: str) -> bool:
        """
        Whether this secret is the asking agent's.

        :param secret: The secret sent with a request.
        :type secret: str
        :return: True for the agent that asked.
        :rtype: bool
        """
        return hmac.compare_digest(self.secret_hash, hash_api_key(secret))


class Pairings:
    """
    Pairings in progress, in Redis: each lasts ``PAIRING_SECONDS``, is
    approved once, and hands over its token once.
    """

    def __init__(self, redis: Redis) -> None:
        """
        Bind to Redis.

        :param redis: Shared Redis client.
        :type redis: Redis
        """
        self.redis = redis

    async def start(
        self, request: PairingRequest, address: str
    ) -> tuple[Pairing, str]:
        """
        Open a pairing for an agent.

        :param request: What the agent says about its machine.
        :type request: PairingRequest
        :param address: Where the request came from.
        :type address: str
        :return: The pairing, and the secret only the agent is given.
        :rtype: tuple[Pairing, str]
        :raises RuntimeError: If no free code turned up.
        """
        secret = secrets.token_urlsafe(SECRET_BYTES)
        for _ in range(CODE_TRIES):
            pairing = Pairing(
                code=new_code(),
                secret_hash=hash_api_key(secret),
                address=address,
                requested_at=datetime.now(UTC).isoformat(),
                **request.model_dump(),
            )
            if await self.keep(pairing):
                return pairing, secret
        raise RuntimeError("No free pairing code")

    async def keep(self, pairing: Pairing) -> bool:
        """
        Store a new pairing, unless its code is already in use.

        :param pairing: The pairing.
        :type pairing: Pairing
        :return: True if stored.
        :rtype: bool
        """
        key = PAIRING_KEY.format(code=pairing.code)
        value = json.dumps(asdict(pairing))
        return bool(
            await self.redis.set(key, value, ex=PAIRING_SECONDS, nx=True)
        )

    async def find(self, code: str) -> Pairing | None:
        """
        The pairing with this code, while it lasts.

        :param code: The code, normalized.
        :type code: str
        :return: The pairing, or None.
        :rtype: Pairing | None
        """
        kept = await self.redis.get(PAIRING_KEY.format(code=code))
        return Pairing(**json.loads(kept)) if kept else None

    async def claim_approval(self, code: str) -> bool:
        """
        Be the one approval of this code: two at once (a double click,
        or two people with one code) cannot both make a cluster.

        :param code: The code.
        :type code: str
        :return: True for the first approval only.
        :rtype: bool
        """
        key = APPROVAL_KEY.format(code=code)
        claimed = await self.redis.set(key, 1, ex=PAIRING_SECONDS, nx=True)
        return bool(claimed)

    async def approve(
        self, pairing: Pairing, owner_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        """
        Record who approved a pairing and the cluster it became; it
        keeps the time it has left.

        :param pairing: The pairing.
        :type pairing: Pairing
        :param owner_id: The person who approved it.
        :type owner_id: uuid.UUID
        :param target_id: The new compute target.
        :type target_id: uuid.UUID
        """
        approved = replace(
            pairing, owner_id=str(owner_id), target_id=str(target_id)
        )
        key = PAIRING_KEY.format(code=pairing.code)
        value = json.dumps(asdict(approved))
        await self.redis.set(key, value, keepttl=True, xx=True)

    async def take(self, code: str) -> Pairing | None:
        """
        Remove a pairing in the same step as reading it (GETDEL), so
        its token is handed over once.

        :param code: The code.
        :type code: str
        :return: The pairing, or None if another request took it.
        :rtype: Pairing | None
        """
        kept = await self.redis.getdel(PAIRING_KEY.format(code=code))
        return Pairing(**json.loads(kept)) if kept else None
