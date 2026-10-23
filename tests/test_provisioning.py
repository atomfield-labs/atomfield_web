"""
Startup provisioning is safe when several API processes start at once.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.security import hash_api_key
from app.main import provision_admin_key
from app.models.api_key import ApiKey


def test_processes_starting_together_create_one_admin_key(
    make_session: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Two processes provision the admin key at the same moment: neither
    fails, and exactly one key exists.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param monkeypatch: Sets a fresh admin key for this test.
    :type monkeypatch: pytest.MonkeyPatch
    """
    monkeypatch.setattr(
        settings, "ADMIN_API_KEY", f"af_admin_race_{uuid.uuid4().hex}"
    )
    key_hash = hash_api_key(settings.ADMIN_API_KEY)

    async def start_process() -> None:
        async with make_session() as session:
            await provision_admin_key(session)

    async def scenario() -> int:
        await asyncio.gather(start_process(), start_process())
        async with make_session() as session:
            count = await session.scalar(
                select(func.count()).where(ApiKey.key_hash == key_hash)
            )
            await session.execute(
                delete(ApiKey).where(ApiKey.key_hash == key_hash)
            )
            await session.commit()
        return count

    assert asyncio.run(scenario()) == 1
