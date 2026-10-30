"""
HTTP routes for a person's API keys, which their scripts use. Keys are
made and revoked only in the web app, signed in.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_browser_user
from app.api.errors import not_found
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import ApiKeyCreateRequest, NewScriptKey, ScriptKeyView
from app.services.accounts import keys_of, new_key, revoke_key

router = APIRouter(prefix="/auth/me/keys", tags=["Authentication"])

KEY_KIND = "Key"


@router.get("", response_model=list[ScriptKeyView])
async def list_my_keys(
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScriptKeyView]:
    """
    The caller's keys that still work, newest first.

    :param user: The person, signed in.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Their keys, without the secrets.
    :rtype: list[ScriptKeyView]
    """
    keys = await keys_of(db, user.id)
    return [ScriptKeyView.model_validate(key) for key in keys]


@router.post(
    "", response_model=NewScriptKey, status_code=status.HTTP_201_CREATED
)
async def make_key(
    payload: ApiKeyCreateRequest,
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
) -> NewScriptKey:
    """
    A new key for the caller's scripts; its secret is shown only now.

    :param payload: What the key is for.
    :type payload: ApiKeyCreateRequest
    :param user: The person, signed in.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The key, with its secret.
    :rtype: NewScriptKey
    """
    secret, key = new_key(user.id, payload.label)
    db.add(key)
    await db.commit()
    await db.refresh(key)
    shown = ScriptKeyView.model_validate(key).model_dump()
    return NewScriptKey(api_key=secret, **shown)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_key(
    key_id: UUID,
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Stop one of the caller's keys working, at once.

    :param key_id: The key.
    :type key_id: UUID
    :param user: The person, signed in.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: An empty answer.
    :rtype: Response
    :raises HTTPException: 404 if it is not theirs, or already revoked.
    """
    if not await revoke_key(db, user.id, key_id):
        raise not_found(KEY_KIND, key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
