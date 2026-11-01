"""
What a finished job leaves behind, as the server records it.

Every file gets a card (path, size, sha256); the files stay on this
machine. A few small text files, logs first, are also uploaded so the
web UI can show them; a log too long for the limit is sent as its end,
which is what the UI shows anyway.
"""

from collections.abc import Sequence
from fnmatch import fnmatchcase
from pathlib import Path

from agent.workspace import own_files
from app.agents.schemas import (
    EXECUTION_LOG,
    MAX_UI_FILES,
    UI_FILE_MAX_BYTES,
    FileCard,
)
from app.core.fingerprints import file_sha256

LOG_SUFFIX = ".log"
# Text a person can read in the browser.
TEXT_SUFFIXES = {
    LOG_SUFFIX,
    ".out",
    ".txt",
    ".xyz",
    ".json",
    ".csv",
    ".dat",
    ".mol",
    ".pdb",
    ".sdf",
    ".inp",
    ".in",
    ".win",
    ".wout",
}
# Order of the files after the script's log and the command's output.
DECLARED_RANK = 2
LOG_RANK = 3
TEXT_RANK = 4


def card_for(path: Path, workspace: Path) -> FileCard:
    """
    One file's card.

    :param path: A file in the job's folder.
    :type path: Path
    :param workspace: The job's folder.
    :type workspace: Path
    :return: Its path in the folder, size and fingerprint.
    :rtype: FileCard
    """
    return FileCard(
        path=path.relative_to(workspace).as_posix(),
        size_bytes=path.stat().st_size,
        sha256=file_sha256(path),
    )


def file_cards(workspace: Path) -> list[FileCard]:
    """
    Card every file the job made (``own_files``): links point at
    earlier jobs' files, carded there.

    Slow for large outputs (hashing reads every byte): run it in a
    thread so heartbeats continue meanwhile.

    :param workspace: The job's folder.
    :type workspace: Path
    :return: Cards sorted by path.
    :rtype: list[FileCard]
    """
    cards = [card_for(path, workspace) for path in own_files(workspace)]
    return sorted(cards, key=lambda card: card.path)


def ui_priority(
    card: FileCard, task_id: str, output_globs: Sequence[str]
) -> tuple[int, str]:
    """
    Order for choosing UI files: the script's log, the command's
    output, what the task says it writes (its plots and summary), other
    logs, then other text.

    :param card: A candidate file.
    :type card: FileCard
    :param task_id: The job's task, which names its log.
    :type task_id: str
    :param output_globs: The patterns of the task's outputs.
    :type output_globs: Sequence[str]
    :return: Sort key; lower comes first.
    :rtype: tuple[int, str]
    """
    first = [f"{task_id}{LOG_SUFFIX}", EXECUTION_LOG]
    if card.path in first:
        return first.index(card.path), card.path
    if any(fnmatchcase(card.path, glob) for glob in output_globs):
        return DECLARED_RANK, card.path
    is_log = card.path.endswith(LOG_SUFFIX)
    return (LOG_RANK if is_log else TEXT_RANK), card.path


def pick_ui_files(
    cards: list[FileCard], task_id: str, output_globs: Sequence[str] = ()
) -> list[str]:
    """
    Choose the small files to upload for the web UI: text files at
    the top of the folder, logs of any size (sent as their end), other
    text only if under the size limit.

    :param cards: Every file of the job.
    :type cards: list[FileCard]
    :param task_id: The job's task.
    :type task_id: str
    :param output_globs: The patterns of the task's outputs, which go
        before other text, so a folder of many small files can't crowd
        them out.
    :type output_globs: Sequence[str]
    :return: Up to ``MAX_UI_FILES`` names, most useful first.
    :rtype: list[str]
    """
    chosen = [
        card
        for card in cards
        if "/" not in card.path
        and Path(card.path).suffix.lower() in TEXT_SUFFIXES
        and (
            card.path.endswith(LOG_SUFFIX)
            or card.size_bytes <= UI_FILE_MAX_BYTES
        )
    ]
    chosen.sort(key=lambda card: ui_priority(card, task_id, output_globs))
    return [card.path for card in chosen[:MAX_UI_FILES]]


def upload_body(path: Path, max_bytes: int = UI_FILE_MAX_BYTES) -> bytes:
    """
    The bytes to upload for a UI file: all of it, or its last
    ``max_bytes`` (the end of a long log).

    :param path: The file.
    :type path: Path
    :param max_bytes: Upload limit.
    :type max_bytes: int
    :return: Content to send.
    :rtype: bytes
    """
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - max_bytes))
        return stream.read()
