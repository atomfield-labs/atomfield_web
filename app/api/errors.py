"""
The HTTP errors the API answers with, built one way each.
"""

from fastapi import HTTPException, status


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
