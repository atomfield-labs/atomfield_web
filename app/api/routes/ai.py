"""
HTTP routes for AI help. A person's key is managed only in the web app,
signed in, as their keys for scripts are, and no route ever returns it.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.keys import choose_model, remove_key, store_key
from app.ai.vault import KeyUnreadableError, KeyVault
from app.ai.vendors import (
    VENDORS,
    AiVendor,
    LlmClient,
    LlmError,
    first_choice,
)
from app.api.dependencies import (
    LlmFactory,
    ai_call_allowed,
    get_browser_user,
    get_key_vault,
    get_llm_factory,
)
from app.api.errors import (
    bad_request,
    conflict,
    not_found,
    too_many_requests,
)
from app.db.session import get_db
from app.models.ai import AiKey
from app.models.user import User
from app.schemas.ai import (
    AiKeySave,
    AiKeySaved,
    AiKeyState,
    AiModelChoice,
    AiVendorView,
    SavedAiKey,
)

router = APIRouter(prefix="/ai", tags=["AI help"])

KEY_KIND = "AI key"
NO_SECRET_MESSAGE = (
    "This server has no AI_KEY_SECRET set, so it can't keep AI keys."
)
SECRET_CHANGED_MESSAGE = (
    "This server's secret has changed since you saved your key. Add it again."
)
TOO_MANY_MESSAGE = "Too many AI requests. Wait a minute and try again."


def vendor_views() -> list[AiVendorView]:
    """
    The vendors someone can choose.

    :return: Each one's id, name and warning.
    :rtype: list[AiVendorView]
    """
    return [
        AiVendorView(id=vendor, title=entry.title, warning=entry.warning)
        for vendor, entry in VENDORS.items()
    ]


def key_state(vault: KeyVault | None, key: AiKey | None) -> AiKeyState:
    """
    What the web app is told about a person's key.

    :param vault: The server's vault; None without a secret.
    :type vault: KeyVault | None
    :param key: Their stored key, if any.
    :type key: AiKey | None
    :return: The state, without the key itself.
    :rtype: AiKeyState
    """
    saved = SavedAiKey.model_validate(key) if key is not None else None
    return AiKeyState(
        available=vault is not None, vendors=vendor_views(), saved=saved
    )


def require_vault(vault: KeyVault | None) -> KeyVault:
    """
    The vault, or a refusal saying why there is none.

    :param vault: The server's vault; None without a secret.
    :type vault: KeyVault | None
    :return: The vault.
    :rtype: KeyVault
    :raises HTTPException: 409 without a secret.
    """
    if vault is None:
        raise conflict(NO_SECRET_MESSAGE)
    return vault


def client_with_key(
    vault: KeyVault, key: AiKey, make_client: LlmFactory
) -> LlmClient:
    """
    A client holding a person's stored key.

    :param vault: Reads the key.
    :type vault: KeyVault
    :param key: The stored key.
    :type key: AiKey
    :param make_client: Makes the client.
    :type make_client: LlmFactory
    :return: The client.
    :rtype: LlmClient
    :raises HTTPException: 409 if the server's secret has changed.
    """
    try:
        return make_client(AiVendor(key.vendor), vault.reveal(key.sealed_key))
    except KeyUnreadableError:
        raise conflict(SECRET_CHANGED_MESSAGE) from None


async def stored_key(db: AsyncSession, user: User) -> AiKey | None:
    """
    A person's key as it is now, after a statement changed it directly.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param user: The person.
    :type user: User
    :return: Their key, if any.
    :rtype: AiKey | None
    """
    return await db.get(AiKey, user.id, populate_existing=True)


@router.get("/key", response_model=AiKeyState)
async def read_my_key(
    user: User = Depends(get_browser_user),
    vault: KeyVault | None = Depends(get_key_vault),
    db: AsyncSession = Depends(get_db),
) -> AiKeyState:
    """
    Whether AI help is on offer, and the caller's key, without the key.

    :param user: The person, signed in.
    :type user: User
    :param vault: The server's vault; None without a secret.
    :type vault: KeyVault | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The state.
    :rtype: AiKeyState
    """
    return key_state(vault, await db.get(AiKey, user.id))


@router.put("/key", response_model=AiKeySaved)
async def save_my_key(
    payload: AiKeySave,
    user: User = Depends(get_browser_user),
    vault: KeyVault | None = Depends(get_key_vault),
    make_client: LlmFactory = Depends(get_llm_factory),
    allowed: bool = Depends(ai_call_allowed),
    db: AsyncSession = Depends(get_db),
) -> AiKeySaved:
    """
    Check a key with its vendor, by asking for its models, then save it.

    :param payload: The vendor and the key.
    :type payload: AiKeySave
    :param user: The person, signed in.
    :type user: User
    :param vault: The server's vault; None without a secret.
    :type vault: KeyVault | None
    :param make_client: Makes a vendor's client.
    :type make_client: LlmFactory
    :param allowed: Whether they are within the limit per minute.
    :type allowed: bool
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The new state, and the models the key can ask.
    :rtype: AiKeySaved
    :raises HTTPException: 429 over the limit, 409 without a secret, 400
        if the vendor refuses the key.
    """
    if not allowed:
        raise too_many_requests(TOO_MANY_MESSAGE)
    keeper = require_vault(vault)
    secret = payload.key.get_secret_value().strip()
    try:
        async with make_client(payload.vendor, secret) as llm:
            models = await llm.list_models()
    except LlmError as error:
        raise bad_request(str(error)) from None
    choice = first_choice(payload.vendor, models)
    await store_key(db, keeper, user.id, payload.vendor, secret, choice)
    state = key_state(keeper, await stored_key(db, user))
    return AiKeySaved(**state.model_dump(), models=models)


@router.get("/key/models", response_model=list[str])
async def list_my_models(
    user: User = Depends(get_browser_user),
    vault: KeyVault | None = Depends(get_key_vault),
    make_client: LlmFactory = Depends(get_llm_factory),
    allowed: bool = Depends(ai_call_allowed),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """
    The models the caller's saved key can ask.

    :param user: The person, signed in.
    :type user: User
    :param vault: The server's vault; None without a secret.
    :type vault: KeyVault | None
    :param make_client: Makes a vendor's client.
    :type make_client: LlmFactory
    :param allowed: Whether they are within the limit per minute.
    :type allowed: bool
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Model names.
    :rtype: list[str]
    :raises HTTPException: 429 over the limit, 409 without a secret, 404
        without a key, 400 if the vendor refuses it.
    """
    if not allowed:
        raise too_many_requests(TOO_MANY_MESSAGE)
    key = await db.get(AiKey, user.id)
    if key is None:
        raise not_found(KEY_KIND, user.id)
    client = client_with_key(require_vault(vault), key, make_client)
    try:
        async with client as llm:
            return await llm.list_models()
    except LlmError as error:
        raise bad_request(str(error)) from None


@router.patch("/key", response_model=AiKeyState)
async def choose_my_model(
    payload: AiModelChoice,
    user: User = Depends(get_browser_user),
    vault: KeyVault | None = Depends(get_key_vault),
    db: AsyncSession = Depends(get_db),
) -> AiKeyState:
    """
    Change the model the caller's key asks.

    :param payload: The model.
    :type payload: AiModelChoice
    :param user: The person, signed in.
    :type user: User
    :param vault: The server's vault; None without a secret.
    :type vault: KeyVault | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The new state.
    :rtype: AiKeyState
    :raises HTTPException: 404 without a key.
    """
    if not await choose_model(db, user.id, payload.model):
        raise not_found(KEY_KIND, user.id)
    return key_state(vault, await stored_key(db, user))


@router.delete("/key", status_code=status.HTTP_204_NO_CONTENT)
async def remove_my_key(
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Forget the caller's key. Doing it twice is fine.

    :param user: The person, signed in.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: An empty answer.
    :rtype: Response
    """
    await remove_key(db, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
