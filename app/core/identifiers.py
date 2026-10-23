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
