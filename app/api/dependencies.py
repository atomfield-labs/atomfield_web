"""
Shared FastAPI route dependencies for database, cache, and authentication.
"""

from arq import ArqRedis
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.api_key import ApiKey


async def get_redis(request: Request) -> ArqRedis:
    """
    Provide the ARQ Redis connection pool from application state.

    :param request: Active FastAPI HTTP request object.
    :type request: Request
    :return: Shared ArqRedis client instance.
    :rtype: ArqRedis
    """
    return request.app.state.redis


async def get_current_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """
    Authenticate client request via SHA-256 hashed X-API-Key header.

    :param x_api_key: Secret API token provided in HTTP request header.
    :type x_api_key: Optional[str]
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Validated and active ApiKey entity.
    :rtype: ApiKey
    :raises HTTPException: 401 if key is missing, invalid, or inactive.
    """
    if not x_api_key:
        error_msg = (
            "API key required. Please provide a valid 'X-API-Key' header."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg,
        )

    key_hash = hash_api_key(x_api_key)
    query = select(ApiKey).where(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active.is_(True),
    )
    result = await db.execute(query)
    api_key = result.scalars().first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or deactivated API key.",
        )

    # Touch last_used_at timestamp asynchronously
    touch_stmt = (
        update(ApiKey)
        .where(ApiKey.id == api_key.id)
        .values(last_used_at=func.now())
    )
    await db.execute(touch_stmt)
    await db.commit()

    return api_key


async def get_optional_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey | None:
    """
    Optionally resolve authenticated API key without enforcing rejection.

    :param x_api_key: Optional API token from header.
    :type x_api_key: Optional[str]
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :return: Resolved ApiKey if present and valid, else None.
    :rtype: Optional[ApiKey]
    """
    if not x_api_key:
        return None
    try:
        return await get_current_api_key(x_api_key=x_api_key, db=db)
    except HTTPException:
        return None


async def require_admin_key(
    api_key: ApiKey = Depends(get_current_api_key),
) -> ApiKey:
    """
    Ensure the calling client holds cluster administrator credentials.

    :param api_key: Authenticated ApiKey entity from request header.
    :type api_key: ApiKey
    :return: Validated administrator ApiKey entity.
    :rtype: ApiKey
    :raises HTTPException: 403 if admin key unconfigured or caller lacks rights.
    """
    if not settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key is not configured on the server.",
        )

    admin_hash = hash_api_key(settings.ADMIN_API_KEY)
    if api_key.key_hash != admin_hash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )

    return api_key
