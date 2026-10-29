"""
The HTTP errors the API answers with, built one way each.
"""

from fastapi import HTTPException, status

# Tells a client refused for going too fast when to try again.
RETRY_AFTER = "Retry-After"


def unauthorized(detail: str, scheme: str | None = None) -> HTTPException:
    """
    A 401: no usable credentials.

    :param detail: Explanation for the client.
    :type detail: str
    :param scheme: The scheme to use (``WWW-Authenticate``), if the
        client should be told, e.g. ``Bearer``.
    :type scheme: str | None
    :return: Exception to raise.
    :rtype: HTTPException
    """
    headers = {"WWW-Authenticate": scheme} if scheme else None
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=headers,
    )


def not_found(kind: str, item_id: object) -> HTTPException:
    """
    A 404 for something missing or someone else's: the same either
    way, so a stranger cannot even learn that an id exists.

    :param kind: What was asked for, e.g. ``Job``.
    :type kind: str
    :param item_id: Its id.
    :type item_id: object
    :return: Exception to raise.
    :rtype: HTTPException
    """
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{kind} {item_id} not found",
    )


def conflict(detail: str) -> HTTPException:
    """
    A 409: the request clashes with how things stand (a job already
    finished, a version published with other contents).

    :param detail: Explanation for the client.
    :type detail: str
    :return: Exception to raise.
    :rtype: HTTPException
    """
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def too_large(detail: str) -> HTTPException:
    """
    A 413: the upload is bigger than this route or link accepts.

    :param detail: Explanation for the client, naming the limit.
    :type detail: str
    :return: Exception to raise.
    :rtype: HTTPException
    """
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=detail
    )


def unprocessable(detail: str) -> HTTPException:
    """
    A 422: the request arrived whole but cannot be used (a wheel agents
    could not run, a file name that is a path).

    :param detail: Explanation for the client.
    :type detail: str
    :return: Exception to raise.
    :rtype: HTTPException
    """
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
    )


def bad_request(detail: str) -> HTTPException:
    """
    A 400: the request cannot be carried out as given (a pipeline whose
    graph has a cycle).

    :param detail: Explanation for the client.
    :type detail: str
    :return: Exception to raise.
    :rtype: HTTPException
    """
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def forbidden(detail: str) -> HTTPException:
    """
    A 403: the caller is known but not allowed (not the administrator,
    or a link not signed for this request).

    :param detail: Explanation for the client.
    :type detail: str
    :return: Exception to raise.
    :rtype: HTTPException
    """
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def too_many_requests(
    detail: str, retry_after_seconds: int | None = None
) -> HTTPException:
    """
    A 429: over a limit (a quota, or how often something may be done).

    :param detail: Explanation for the client.
    :type detail: str
    :param retry_after_seconds: When to try again, if waiting helps.
    :type retry_after_seconds: int | None
    :return: Exception to raise.
    :rtype: HTTPException
    """
    waiting_helps = retry_after_seconds is not None
    headers = {RETRY_AFTER: str(retry_after_seconds)} if waiting_helps else None
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers=headers,
    )
