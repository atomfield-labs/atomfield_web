"""
What a finished job leaves behind, as the server records it.

Every file gets a card (path, size, sha256); the files stay on this
machine. A few small text files, logs first, are also uploaded so the
web UI can show them; a log too long for the limit is sent as its end,
which is what the UI shows anyway.
"""

import hashlib
import os
from pathlib import Path

from app.agents.schemas import (
    EXECUTION_LOG,
    MAX_UI_FILES,
    UI_FILE_MAX_BYTES,
    FileCard,
)

UPSTREAM_DIR = "upstream"
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
    ".inp",
}
HASH_CHUNK_BYTES = 1024 * 1024


def sha256_of(path: Path) -> str:
    """
    Fingerprint a file's content, reading it in chunks.

    :param path: The file.
    :type path: Path
    :return: SHA-256 as hex.
    :rtype: str
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def file_cards(workspace: Path) -> list[FileCard]:
    """
    Card every file in a job's folder, walking subfolders but not
    links (``upstream/`` and any other link point at earlier jobs'
    files, carded there) or hidden files.

    Slow for large outputs (hashing reads every byte): run it in a
    thread so heartbeats continue meanwhile.

    :param workspace: The job's folder.
    :type workspace: Path
    :return: Cards sorted by path.
    :rtype: list[FileCard]
    """
    cards = []
    for folder, subfolders, names in os.walk(workspace):
        if Path(folder) == workspace and UPSTREAM_DIR in subfolders:
            subfolders.remove(UPSTREAM_DIR)
        for name in names:
            path = Path(folder) / name
            if name.startswith(".") or path.is_symlink() or not path.is_file():
                continue
            cards.append(
                FileCard(
                    path=path.relative_to(workspace).as_posix(),
                    size_bytes=path.stat().st_size,
                    sha256=sha256_of(path),
                )
            )
    return sorted(cards, key=lambda card: card.path)


def ui_priority(card: FileCard, task_id: str) -> tuple[int, str]:
    """
    Order for choosing UI files: the script's log, the command's
    output, other logs, then other text.

    :param card: A candidate file.
    :type card: FileCard
    :param task_id: The job's task, which names its log.
    :type task_id: str
    :return: Sort key; lower comes first.
    :rtype: tuple[int, str]
    """
    first = [f"{task_id}{LOG_SUFFIX}", EXECUTION_LOG]
    if card.path in first:
        return first.index(card.path), card.path
    is_log = card.path.endswith(LOG_SUFFIX)
    return (2 if is_log else 3), card.path


def pick_ui_files(cards: list[FileCard], task_id: str) -> list[str]:
    """
    Choose the small files to upload for the web UI: text files at
    the top of the folder, logs of any size (sent as their end), other
    text only if under the size limit.

    :param cards: Every file of the job.
    :type cards: list[FileCard]
    :param task_id: The job's task.
    :type task_id: str
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
    chosen.sort(key=lambda card: ui_priority(card, task_id))
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
