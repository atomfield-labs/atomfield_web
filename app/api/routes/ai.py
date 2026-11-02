"""
HTTP routes for AI help. A person's key is managed only in the web app,
signed in, as their keys for scripts are, and no route ever returns it.
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.keys import choose_model, remove_key, store_key
from app.ai.reviews import (
    INTERRUPTED,
    ReviewRunner,
    is_stale,
    kind_for,
    latest_review,
    start_review,
)
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
    get_owned_job,
    get_review_runner,
    get_store,
)
from app.api.errors import (
    bad_request,
    conflict,
    not_found,
    too_many_requests,
)
from app.db.session import get_db
from app.models.ai import AiKey, AiReview, ReviewStatus
from app.models.job import Job
from app.models.user import User
from app.schemas.ai import (
    AiKeySave,
    AiKeySaved,
    AiKeyState,
    AiModelChoice,
    AiReviewState,
    AiReviewView,
    AiVendorView,
    SavedAiKey,
)
from app.storage.keys import ai_sent_key
from app.storage.store import ArtifactStore

router = APIRouter(prefix="/ai", tags=["AI help"])
reviews_router = APIRouter(prefix="/jobs/{job_id}/ai-reviews", tags=["AI help"])

KEY_KIND = "AI key"
SENT_TEXT_KIND = "Text sent"
# What was sent came partly from a job: a browser must never treat it as
# a page.
NEVER_A_PAGE = {"X-Content-Type-Options": "nosniff"}
NO_KEY_MESSAGE = "Add an AI key first."
NOT_ENDED_MESSAGE = "Only a step that failed or finished can be reviewed."
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


def review_view(review: AiReview) -> AiReviewView:
    """
    A review as the AI tab shows it. One lost with its server reads as
    failed, so the tab doesn't spin for ever.

    :param review: The review.
    :type review: AiReview
    :return: The view.
    :rtype: AiReviewView
    """
    view = AiReviewView.model_validate(review)
    if is_stale(review):
        return view.model_copy(
            update={"status": ReviewStatus.FAILED, "error": INTERRUPTED}
        )
    return view


@reviews_router.post(
    "",
    response_model=AiReviewView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_my_review(
    tasks: BackgroundTasks,
    job: Job = Depends(get_owned_job),
    user: User = Depends(get_browser_user),
    runner: ReviewRunner | None = Depends(get_review_runner),
    allowed: bool = Depends(ai_call_allowed),
    db: AsyncSession = Depends(get_db),
) -> AiReviewView:
    """
    Start a review of a step that ended, paid for by the caller's key. The
    answer goes at once, and the work carries on after it. If one is
    already running, that one is the answer.

    :param tasks: Runs the review after the answer has gone.
    :type tasks: BackgroundTasks
    :param job: A job the caller may act on.
    :type job: Job
    :param user: The person, signed in.
    :type user: User
    :param runner: Runs reviews; None if this server has no secret.
    :type runner: ReviewRunner | None
    :param allowed: Whether they are within the limit per minute.
    :type allowed: bool
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The review, still running.
    :rtype: AiReviewView
    :raises HTTPException: 409 if the step hasn't ended or there is no key
        or secret; 429 over the limit.
    """
    kind = kind_for(job)
    if kind is None:
        raise conflict(NOT_ENDED_MESSAGE)
    if not allowed:
        raise too_many_requests(TOO_MANY_MESSAGE)
    if runner is None:
        raise conflict(NO_SECRET_MESSAGE)
    key = await db.get(AiKey, user.id)
    if key is None:
        raise conflict(NO_KEY_MESSAGE)
    review, is_new = await start_review(db, job, kind, key)
    if is_new:
        tasks.add_task(runner.run, review.id)
    return review_view(review)


@reviews_router.get("/latest", response_model=AiReviewState)
async def read_latest_review(
    job: Job = Depends(get_owned_job),
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
) -> AiReviewState:
    """
    What can be asked about a step, and its newest answer, which the AI
    tab shows and asks after.

    :param job: A job the caller may act on.
    :type job: Job
    :param user: The person, signed in.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The kind of review it can have, and the review, if any.
    :rtype: AiReviewState
    """
    review = await latest_review(db, job.id)
    shown = review_view(review) if review is not None else None
    return AiReviewState(kind=kind_for(job), review=shown)


@reviews_router.get("/{review_id}/sent", response_class=PlainTextResponse)
async def read_sent_text(
    review_id: UUID,
    job: Job = Depends(get_owned_job),
    user: User = Depends(get_browser_user),
    store: ArtifactStore = Depends(get_store),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """
    The exact text a model read for a review.

    :param review_id: The review.
    :type review_id: UUID
    :param job: A job the caller may act on.
    :type job: Job
    :param user: The person, signed in.
    :type user: User
    :param store: Where the text is kept.
    :type store: ArtifactStore
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: The text.
    :rtype: PlainTextResponse
    :raises HTTPException: 404 if it isn't this job's, or nothing was sent.
    """
    review = await db.get(AiReview, review_id)
    if review is None or review.job_id != job.id:
        raise not_found(SENT_TEXT_KIND, review_id)
    content = await store.read(ai_sent_key(job.run_id, review_id))
    if content is None:
        raise not_found(SENT_TEXT_KIND, review_id)
    return PlainTextResponse(content, headers=NEVER_A_PAGE)
