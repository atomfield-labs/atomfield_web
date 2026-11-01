"""
A public repository holds the example's values, so a server must never
run on them.
"""

from pathlib import Path

import pytest

from app.core.config import (
    PLACEHOLDER,
    SECRET_SETTINGS,
    Settings,
    refuse_placeholders,
)

EXAMPLE_FILE = Path(__file__).resolve().parents[1] / ".env.example"
A_REAL_VALUE = "a-value-someone-generated"


def test_a_secret_left_as_the_placeholder_stops_the_server() -> None:
    """
    The message names the setting to fix.
    """
    current = Settings(_env_file=None, ADMIN_API_KEY=PLACEHOLDER)

    with pytest.raises(RuntimeError, match="ADMIN_API_KEY"):
        refuse_placeholders(current)


def test_the_message_names_settings_not_values() -> None:
    """
    Other secrets in the same file never reach the log.
    """
    current = Settings(
        _env_file=None,
        ADMIN_API_KEY=PLACEHOLDER,
        STORAGE_SIGNING_KEY=A_REAL_VALUE,
    )

    with pytest.raises(RuntimeError) as caught:
        refuse_placeholders(current)

    assert A_REAL_VALUE not in str(caught.value)
    assert "STORAGE_SIGNING_KEY" not in str(caught.value)


def test_real_or_empty_secrets_pass() -> None:
    """
    A generated value is fine, and so is one left out: a server with no
    sign-in or no house agent simply goes without.
    """
    refuse_placeholders(Settings(_env_file=None, ADMIN_API_KEY=A_REAL_VALUE))
    refuse_placeholders(Settings(_env_file=None, ADMIN_API_KEY=None))


def test_every_placeholder_in_the_example_is_refused() -> None:
    """
    A secret added to the example with the placeholder is caught too.
    """
    lines = EXAMPLE_FILE.read_text().splitlines()
    placeholders = [
        line.split("=", 1)[0]
        for line in lines
        if line.endswith(f"={PLACEHOLDER}")
    ]

    assert placeholders
    assert set(placeholders) <= set(SECRET_SETTINGS)
