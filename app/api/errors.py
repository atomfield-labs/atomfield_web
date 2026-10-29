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
