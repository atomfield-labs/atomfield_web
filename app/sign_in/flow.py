"""
The sign-in flow, from the button to the signed-in person.

Starting: make the sign-in's secrets, keep them in Redis for a few
minutes, and send the browser to the provider. Finishing: the answer
must come back to the browser that started, and only once; the
provider must vouch for the account; and the person must be an owner
or on a lab's list. Nobody else gets in, so strangers leave no trace.
"""

import json
from dataclasses import asdict, dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.accounts import (
    listed_person_signing_in,
    owner_signing_in,
)
from app.sign_in.provider import IdentityProvider, SignInStart
from app.sign_in.refusals import SignInProblem, SignInRefused

PENDING_KEY = "sign-in:{state}"
# Long enough to type a password and approve a prompt on a phone.
PENDING_SECONDS = 600


class PendingSignIns:
    """
    Sign-ins started but not yet finished, kept in Redis: each can be
    finished once, within ``PENDING_SECONDS``.
    """

    def __init__(self, redis: Redis) -> None:
        """
        Bind to Redis.

        :param redis: Shared Redis client.
        :type redis: Redis
        """
        self.redis = redis

    async def remember(self, start: SignInStart) -> None:
        """
        Keep a new sign-in's secrets until it finishes or expires.

        :param start: The sign-in's secrets.
        :type start: SignInStart
        """
        key = PENDING_KEY.format(state=start.state)
        await self.redis.set(key, json.dumps(asdict(start)), ex=PENDING_SECONDS)

    async def take(self, state: str) -> SignInStart | None:
        """
        The sign-in with this state, removed in the same step (GETDEL),
        so one answer from the provider can never be used twice.

        :param state: The state the provider's answer carries.
        :type state: str
        :return: The sign-in's secrets, or None if it is unknown,
            expired or already finished.
        :rtype: SignInStart | None
        """
        kept = await self.redis.getdel(PENDING_KEY.format(state=state))
        return SignInStart(**json.loads(kept)) if kept else None


@dataclass(frozen=True, slots=True)
class LoginRedirect:
    """
    Where to send the browser to sign in, and the state its cookie
    must bring back.

    :param link: The provider's sign-in page for this sign-in.
    :type link: str
    :param state: The sign-in's state.
    :type state: str
    """

    link: str
    state: str


class SignInFlow:
    """
    Signs people in: the provider says who they are; the list of owners
    and the labs' lists say whether they may enter.
    """

    def __init__(
        self,
        provider: IdentityProvider,
        pending: PendingSignIns,
        owners: frozenset[str],
    ) -> None:
        """
        Wire the flow.

        :param provider: The sign-in provider.
        :type provider: IdentityProvider
        :param pending: Sign-ins in progress.
        :type pending: PendingSignIns
        :param owners: Emails of the platform's owners.
        :type owners: frozenset[str]
        """
        self.provider = provider
        self.pending = pending
        self.owners = owners

    async def begin(self) -> LoginRedirect:
        """
        Start a sign-in.

        :return: Where to send the browser, and the state its cookie
            must keep.
        :rtype: LoginRedirect
        """
        start = SignInStart.new()
        await self.pending.remember(start)
        link = await self.provider.login_link(start)
        return LoginRedirect(link=link, state=start.state)

    async def started_here(self, state: str, browser_state: str) -> SignInStart:
        """
        The sign-in the provider is answering, if this browser started
        it (its cookie holds the same state) and it is still pending.
        Without the cookie check, someone could start a sign-in with
        their own account and lead another person's browser to finish
        it, signing that person in as them.

        :param state: The state in the provider's answer.
        :type state: str
        :param browser_state: The state in this browser's cookie.
        :type browser_state: str
        :return: The sign-in's secrets.
        :rtype: SignInStart
        :raises SignInRefused: If it began elsewhere, has expired, or
            has already finished.
        """
        here = bool(state) and state == browser_state
        start = await self.pending.take(state) if here else None
        if start is None:
            raise SignInRefused(SignInProblem.EXPIRED)
        return start

    async def finish(
        self, db: AsyncSession, state: str, code: str, browser_state: str
    ) -> User:
        """
        Finish a sign-in with the provider's answer.

        :param db: Asynchronous database session; the caller commits.
        :type db: AsyncSession
        :param state: The state in the answer.
        :type state: str
        :param code: The code in the answer; empty if the person said
            no at the provider.
        :type code: str
        :param browser_state: The state in this browser's cookie.
        :type browser_state: str
        :return: The person, who may enter.
        :rtype: User
        :raises SignInRefused: Saying why they may not.
        """
        start = await self.started_here(state, browser_state)
        if not code:
            raise SignInRefused(SignInProblem.DENIED)
        identity = await self.provider.identity(code, start)
        if identity.email in self.owners:
            user = await owner_signing_in(db, identity)
        else:
            user = await listed_person_signing_in(db, identity)
        if user is None:
            raise SignInRefused(SignInProblem.OUTSIDE, identity.email)
        if not user.is_active:
            raise SignInRefused(SignInProblem.DISABLED)
        return user
