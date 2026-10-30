"""
HTTP routes for signing in with an institute account, identity, and
usage analytics.
"""

from datetime import timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    Caller,
    check_origin,
    get_caller,
    get_sign_in,
    sign_in_allowed,
)
from app.core.config import settings
from app.core.security import SESSION_COOKIE
from app.db.session import get_db
from app.models.job import Job
from app.schemas.auth import (
    ApiKeyInfoResponse,
    UserStatsResponse,
    account_view,
)
from app.services.accounts import sign_in_browser, sign_out_browser
from app.services.job_stats import job_counts
from app.sign_in.flow import PENDING_SECONDS, SignInFlow
from app.sign_in.refusals import SignInProblem, SignInRefused

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Holds a sign-in's state from the button until the provider answers.
SIGN_IN_COOKIE = "atomfield_sign_in"
SAME_SITE = "lax"
# Where the web app lives; told why, if a sign-in is refused.
WEB_APP = "/"
SIGN_IN_ERROR = "sign_in_error"


def cookie_rules() -> dict[str, bool | str]:
    """
    How AtomField's cookies are set: out of reach of page scripts
    (HttpOnly), sent over https only when the server is reached over
    https (Secure), and kept off other sites' background requests and
    form posts (SameSite=Lax).

    :return: Keyword arguments for setting and deleting a cookie.
    :rtype: dict[str, bool | str]
    """
    secure = settings.secure_cookies
    return {"httponly": True, "secure": secure, "samesite": SAME_SITE}


def back_to_web_app(link: str) -> RedirectResponse:
    """
    Send the browser to the web app; the sign-in cookie is done with.

    :param link: Where in the web app.
    :type link: str
    :return: The redirect.
    :rtype: RedirectResponse
    """
    response = RedirectResponse(link, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SIGN_IN_COOKIE, **cookie_rules())
    return response


def refused(problem: SignInProblem) -> RedirectResponse:
    """
    Back to the web app, told why the sign-in was refused.

    :param problem: Why.
    :type problem: SignInProblem
    :return: The redirect.
    :rtype: RedirectResponse
    """
    query = urlencode({SIGN_IN_ERROR: problem.value})
    return back_to_web_app(f"{WEB_APP}?{query}")


def signed_in(token: str, lifetime: timedelta) -> RedirectResponse:
    """
    Back to the web app, signed in: the browser keeps the session's
    secret in a cookie for as long as the session lasts.

    :param token: The session's secret.
    :type token: str
    :param lifetime: How long the session lasts.
    :type lifetime: timedelta
    :return: The redirect.
    :rtype: RedirectResponse
    """
    response = back_to_web_app(WEB_APP)
    max_age = int(lifetime.total_seconds())
    rules = cookie_rules()
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, **rules)
    return response


@router.get("/login")
async def begin_sign_in(
    flow: SignInFlow | None = Depends(get_sign_in),
    allowed: bool = Depends(sign_in_allowed),
) -> RedirectResponse:
    """
    Send the browser to the provider to sign in; it comes back to
    ``/callback``.

    :param flow: The sign-in flow, if sign-in is set up.
    :type flow: SignInFlow | None
    :param allowed: Whether this address may start another sign-in.
    :type allowed: bool
    :return: Redirect to the provider's sign-in page.
    :rtype: RedirectResponse
    """
    if flow is None:
        return refused(SignInProblem.UNAVAILABLE)
    if not allowed:
        return refused(SignInProblem.BUSY)
    redirect = await flow.begin()
    response = RedirectResponse(
        redirect.link, status_code=status.HTTP_303_SEE_OTHER
    )
    response.set_cookie(
        SIGN_IN_COOKIE,
        redirect.state,
        max_age=PENDING_SECONDS,
        **cookie_rules(),
    )
    return response


@router.get("/callback")
async def finish_sign_in(
    state: str = "",
    code: str = "",
    browser_state: str = Cookie("", alias=SIGN_IN_COOKIE),
    flow: SignInFlow | None = Depends(get_sign_in),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Where the provider sends the browser back: sign the person in, or
    tell the web app why not.

    :param state: The sign-in's state, from the provider.
    :type state: str
    :param code: The code to redeem; absent if the person said no.
    :type code: str
    :param browser_state: The state in this browser's sign-in cookie.
    :type browser_state: str
    :param flow: The sign-in flow, if sign-in is set up.
    :type flow: SignInFlow | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Redirect to the web app.
    :rtype: RedirectResponse
    """
    if flow is None:
        return refused(SignInProblem.UNAVAILABLE)
    try:
        user = await flow.finish(db, state, code, browser_state)
    except SignInRefused as refusal:
        return refused(refusal.problem)
    lifetime = timedelta(days=settings.SESSION_DAYS)
    token = await sign_in_browser(db, user.id, lifetime)
    return signed_in(token, lifetime)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_origin)],
)
async def sign_out(
    session_token: str | None = Cookie(None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Sign this browser out: the session ends on the server, and the
    browser forgets its cookie.

    :param session_token: The secret from the session cookie, if any.
    :type session_token: str | None
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: An empty answer.
    :rtype: Response
    """
    if session_token:
        await sign_out_browser(db, session_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, **cookie_rules())
    return response


@router.get("/me", response_model=ApiKeyInfoResponse)
async def get_current_user_info(
    caller: Caller = Depends(get_caller),
) -> ApiKeyInfoResponse:
    """
    Fetch identity metadata and calculation quotas for the caller.

    :param caller: The person, and the key they used if any.
    :type caller: Caller
    :return: User account identity and remaining calculation balance.
    :rtype: ApiKeyInfoResponse
    """
    return account_view(ApiKeyInfoResponse, caller.user, caller.key_prefix)


@router.get("/stats", response_model=UserStatsResponse)
async def get_user_statistics(
    caller: Caller = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
) -> UserStatsResponse:
    """
    Aggregate calculation statistics and failure breakdowns for the caller.

    :param caller: The person, and the key they used if any.
    :type caller: Caller
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Comprehensive execution metrics dictionary.
    :rtype: UserStatsResponse
    """
    counts = await job_counts(db, Job.owner_id == caller.user.id)
    stats = account_view(UserStatsResponse, caller.user, caller.key_prefix)
    return stats.model_copy(update=counts.model_dump())
