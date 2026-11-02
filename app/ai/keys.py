"""
Each person's AI key in the database. What goes in is already encrypted;
what comes out is read only to call the vendor.
"""

import uuid

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.vault import KeyVault
from app.ai.vendors import AiVendor
from app.models.ai import KEY_ENDING_LENGTH, AiKey


async def store_key(
    db: AsyncSession,
    vault: KeyVault,
    user_id: uuid.UUID,
    vendor: AiVendor,
    key: str,
    model: str,
) -> None:
    """
    Save a person's key, replacing the one they had.

    :param db: Asynchronous database session; committed here.
    :type db: AsyncSession
    :param vault: Encrypts the key.
    :type vault: KeyVault
    :param user_id: The person.
    :type user_id: uuid.UUID
    :param vendor: Its vendor.
    :type vendor: AiVendor
    :param key: The key, already checked with the vendor.
    :type key: str
    :param model: The model to start with.
    :type model: str
    """
    values = {
        "vendor": vendor.value,
        "model": model,
        "sealed_key": vault.seal(key),
        "key_ending": key[-KEY_ENDING_LENGTH:],
    }
    statement = insert(AiKey).values(user_id=user_id, **values)
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[AiKey.user_id], set_=values
        )
    )
    await db.commit()


async def choose_model(
    db: AsyncSession, user_id: uuid.UUID, model: str
) -> bool:
    """
    Change the model a person's key asks.

    :param db: Asynchronous database session; committed here.
    :type db: AsyncSession
    :param user_id: The person.
    :type user_id: uuid.UUID
    :param model: The model.
    :type model: str
    :return: False if they have no key.
    :rtype: bool
    """
    statement = (
        update(AiKey)
        .where(AiKey.user_id == user_id)
        .values(model=model)
        .returning(AiKey.user_id)
    )
    changed = (await db.execute(statement)).first()
    await db.commit()
    return changed is not None


async def remove_key(db: AsyncSession, user_id: uuid.UUID) -> None:
    """
    Forget a person's key.

    :param db: Asynchronous database session; committed here.
    :type db: AsyncSession
    :param user_id: The person.
    :type user_id: uuid.UUID
    """
    await db.execute(delete(AiKey).where(AiKey.user_id == user_id))
    await db.commit()
