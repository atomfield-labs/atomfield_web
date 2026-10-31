"""
How the command-line programs end when a person stops them: Ctrl+C,
or Ctrl+D at a question, gives a one-line note and exit code 130, not
a traceback; a server that cannot be reached is one line too.
"""

import subprocess
import sys
from pathlib import Path

import pytest

import agent.ship
from agent.config import write_settings
from app.core.cli import EXIT_INTERRUPTED, stops_cleanly
from app.releases.publish import on_server, upload
from app.releases.publish_data import server_has
from app.releases.tools import PublishError

REPO_ROOT = Path(__file__).resolve().parents[1]
# Nothing listens there.
UNREACHABLE_API = "http://127.0.0.1:9"


@pytest.mark.parametrize("stop", [KeyboardInterrupt, EOFError])
def test_a_stopped_command_says_so_instead_of_a_traceback(
    capsys: pytest.CaptureFixture, stop: type[BaseException]
):
    """
    Ctrl+C (KeyboardInterrupt) or Ctrl+D at a question (EOFError) ends
    the command with its note and the shell's code for "stopped".

    :param capsys: Captured output.
    :type capsys: pytest.CaptureFixture
    :param stop: What the key press raises.
    :type stop: type[BaseException]
    """

    @stops_cleanly("Stopped; nothing was saved.")
    def command() -> int:
        """
        Stopped half-way.

        :return: Never returns.
        :rtype: int
        """
        raise stop

    assert command() == EXIT_INTERRUPTED
    assert capsys.readouterr().err == "\nStopped; nothing was saved.\n"


def test_a_command_that_finishes_is_left_alone():
    """
    Without a key press, the command's own exit code comes through.
    """
    assert stops_cleanly("Stopped.")(lambda: 3)() == 3


def test_login_ended_at_a_question_saves_nothing(tmp_path: Path):
    """
    Ctrl+D at the first question (here, input that ends at once) gives
    the note, no traceback, and leaves the saved settings unchanged.

    :param tmp_path: Empty folder.
    :type tmp_path: Path
    """
    path = tmp_path / "agent.toml"
    write_settings(path, {"api_url": UNREACHABLE_API, "token": "af_agent_x"})
    before = path.read_text()

    done = subprocess.run(
        [sys.executable, "-m", "agent", "login", "--config", str(path)],
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )

    assert done.returncode == EXIT_INTERRUPTED
    assert "Login stopped; nothing was saved." in done.stderr
    assert "Traceback" not in done.stderr
    assert path.read_text() == before


def test_a_stopped_ship_says_how_to_finish(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """
    Ctrl+C while ssh copies the agent ends with what to do next.

    :param monkeypatch: Replaces ssh with a key press.
    :type monkeypatch: pytest.MonkeyPatch
    :param capsys: Captured output.
    :type capsys: pytest.CaptureFixture
    """

    def pressed_ctrl_c(*args, **kwargs):
        """
        ssh, interrupted.

        :raises KeyboardInterrupt: Always.
        """
        raise KeyboardInterrupt

    monkeypatch.setattr(agent.ship.subprocess, "run", pressed_ctrl_c)

    assert agent.ship.main(["mycluster"]) == EXIT_INTERRUPTED
    assert "Run the same command again" in capsys.readouterr().err


def test_publishing_to_a_server_that_is_not_there_is_one_line():
    """
    An unreachable API is a PublishError naming it, which the command
    prints as one line, not a connection traceback; asking whether it
    has a release before building one is the same.
    """
    with pytest.raises(PublishError, match="Could not reach"):
        upload(UNREACHABLE_API, "admin", b"not really a bundle", "abc1234")
    with pytest.raises(PublishError, match="Could not reach"):
        on_server(UNREACHABLE_API, "toy", "1.0")


def test_asking_a_server_that_is_not_there_for_a_pack_is_one_line():
    """
    Before sending a data pack, the command asks the API whether it has
    it; an unreachable API is a PublishError naming it there too.
    """
    with pytest.raises(PublishError, match="Could not reach"):
        server_has(UNREACHABLE_API, "toy-data", "1", "0" * 64)
