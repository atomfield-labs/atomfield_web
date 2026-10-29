"""
Safe identifiers for folder names built from user input.

Kept free of server imports so the agent, which runs on machines
without the API's dependencies, names folders exactly as the API does.
"""

import re
import uuid

UNSAFE_CHARACTERS = re.compile(r"[^a-zA-Z0-9_\-]")
MAX_IDENTIFIER_LENGTH = 64


def sanitize_identifier(name: str) -> str:
    """
    Sanitize identifier to prevent directory traversal and injection.

    :param name: Raw input string to sanitize.
    :type name: str
    :return: Clean alphanumeric identifier string.
    :rtype: str
    """
    clean_name = UNSAFE_CHARACTERS.sub("", name)
    fallback_id = f"id_{uuid.uuid4().hex[:8]}"
    return clean_name[:MAX_IDENTIFIER_LENGTH] or fallback_id


def user_folder_name(user_id: uuid.UUID) -> str:
    """
    Name the folder (and ``user_id`` parameter) of one user.

    :param user_id: The person.
    :type user_id: uuid.UUID
    :return: Folder name such as ``user_1a2b3c4d5e6f``.
    :rtype: str
    """
    return f"user_{user_id.hex[:12]}"


def assign_node_keys(names: list[str]) -> dict[str, str]:
    """
    Give each pipeline node a folder name unique within its run.

    Names are cleaned with ``sanitize_identifier``; two names that clean
    to the same text (``opt 1`` and ``opt1``) get ``_2``, ``_3``...
    Cleaned names hold no dots, so they can never collide with
    ``run.json`` or a retired attempt's ``<name>.try1`` folder.

    :param names: Node names (UI ids), unique among themselves.
    :type names: list[str]
    :return: Name -> folder name.
    :rtype: dict[str, str]
    """
    keys: dict[str, str] = {}
    taken: set[str] = set()
    for name in names:
        base = sanitize_identifier(name)
        key, number = base, 1
        while key in taken:
            number += 1
            key = f"{base}_{number}"
        taken.add(key)
        keys[name] = key
    return keys
