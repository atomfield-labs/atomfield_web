"""
Tests for operator commands. The real wipe is never run here.
"""

import pytest

from app.cli import EXIT_NOT_CONFIRMED, main


def test_wipe_does_nothing_without_confirmation(
    capsys: pytest.CaptureFixture[str],
):
    """
    Without --yes, wipe only says what it would delete, then exits 1.

    :param capsys: Captures what the command prints.
    :type capsys: pytest.CaptureFixture[str]
    """
    assert main(["wipe"]) == EXIT_NOT_CONFIRMED
    assert "Re-run with --yes" in capsys.readouterr().out


def test_unknown_command_is_rejected():
    """
    An unknown sub-command exits with a usage error.
    """
    with pytest.raises(SystemExit):
        main(["drop-everything"])
