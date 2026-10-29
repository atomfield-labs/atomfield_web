"""
A user's quota holds even when submissions arrive at the same moment.
"""

import asyncio
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import hash_api_key
from app.models.api_key import ApiKey
from app.models.run import Run
from app.models.user import User
from app.queue.job_queue import RedisJobQueue
from app.schemas.job import PipelineSubmitRequest
from app.services.job_service import submit_pipeline
from tests.stores import make_redis
from tests.test_agent_api import drain_queue

ONE_JOB = PipelineSubmitRequest.model_validate(
    {
        "nodes": [{"ui_id": "a", "script_name": "toy_opt"}],
        "edges": [],
        "files": [{"filename": "water.xyz", "content": "1\n\nO 0 0 0\n"}],
    }
)


class SlowStore:
    """
    Keeps nothing, slowly: each write takes a moment, so a second
    submission arrives while the first is still on its way.
    """

    async def write(self, key: str, data: bytes) -> None:
        """
        Take a moment.

        :param key: Where the file would go.
        :type key: str
        :param data: Its content.
        :type data: bytes
        """
        await asyncio.sleep(0.2)


async def room_for_one(make_session: async_sessionmaker, secret: str):
    """
    Give a user room for exactly one more job.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param secret: The user's key.
    :type secret: str
    :return: The user's id.
    :rtype: uuid.UUID
    """
    owner = select(ApiKey.user_id).where(
        ApiKey.key_hash == hash_api_key(secret)
    )
    async with make_session() as session:
        statement = (
            update(User)
            .where(User.id == owner.scalar_subquery())
            .values(quota_limit=1, quota_used=0)
            .returning(User.id)
        )
        user_id = (await session.execute(statement)).scalar_one()
        await session.commit()
        return user_id


async def submit_twice(
    make_session: async_sessionmaker, user_id: uuid.UUID
) -> list:
    """
    Submit one job twice at the same moment, each submission in its own
    session with the user as it read them.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param user_id: The user.
    :type user_id: uuid.UUID
    :return: Each submission's summary, or the error it raised.
    :rtype: list
    """
    redis = make_redis()
    queue = RedisJobQueue(redis)
    try:
        async with make_session() as first, make_session() as second:
            sessions = (first, second)
            users = [await session.get(User, user_id) for session in sessions]
            submissions = [
                submit_pipeline(session, ONE_JOB, queue, SlowStore(), user)
                for session, user in zip(sessions, users, strict=True)
            ]
            return await asyncio.gather(*submissions, return_exceptions=True)
    finally:
        await redis.aclose()


async def spent(make_session: async_sessionmaker, user_id: uuid.UUID):
    """
    How much of the quota is counted, and how many runs were made.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param user_id: The user.
    :type user_id: uuid.UUID
    :return: (quota used, runs owned).
    :rtype: tuple[int, int]
    """
    async with make_session() as session:
        used = (await session.get(User, user_id)).quota_used
        runs = select(func.count(Run.id)).where(Run.owner_id == user_id)
        return used, (await session.execute(runs)).scalar_one()


def test_two_submissions_at_once_cannot_both_spend_the_last_of_a_quota(
    make_user_headers, make_session: async_sessionmaker
):
    """
    A user with room for one more job submits twice at the same moment;
    each submission read the quota before the other counted itself.
    One runs, the other is refused, and the quota counts what ran.

    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    secret = make_user_headers()["X-API-Key"]
    user_id = asyncio.run(room_for_one(make_session, secret))
    outcomes = asyncio.run(submit_twice(make_session, user_id))
    drain_queue()
    refused = [item for item in outcomes if isinstance(item, HTTPException)]
    assert [error.status_code for error in refused] == [
        status.HTTP_429_TOO_MANY_REQUESTS
    ]
    assert asyncio.run(spent(make_session, user_id)) == (1, 1)
