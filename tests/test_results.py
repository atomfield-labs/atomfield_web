"""
What a finished job reports: a card per file, and the few small text
files the web UI shows (logs first, a long log as its end).
"""

import hashlib
from pathlib import Path

from agent.results import file_cards, pick_ui_files, upload_body
from app.agents.schemas import MAX_UI_FILES, UI_FILE_MAX_BYTES, FileCard


def card(path: str, size: int = 10) -> FileCard:
    """
    A card for a file of a given size.

    :param path: Path in the job's folder.
    :type path: str
    :param size: Size in bytes.
    :type size: int
    :return: Card.
    :rtype: FileCard
    """
    return FileCard(path=path, size_bytes=size, sha256="0" * 64)


def test_cards_cover_subfolders_but_not_parents_or_hidden_files(
    tmp_path: Path,
):
    """
    Nested outputs are carded; ``upstream/`` links, links to a
    parent's files and hidden files (half-written downloads) are not.

    :param tmp_path: A job folder.
    :type tmp_path: Path
    """
    (tmp_path / "md").mkdir()
    (tmp_path / "md" / "frames.trj").write_bytes(b"frames")
    (tmp_path / "md.log").write_text("log")
    (tmp_path / ".water.xyz.part").write_text("partial")
    parent = tmp_path.parent / "opt"
    parent.mkdir()
    (parent / "opt.xyz").write_text("parent")
    (tmp_path / "upstream").mkdir()
    (tmp_path / "upstream" / "opt").symlink_to(parent)
    (tmp_path / "opt.xyz").symlink_to(parent / "opt.xyz")

    cards = file_cards(tmp_path)

    assert [item.path for item in cards] == ["md.log", "md/frames.trj"]
    assert cards[1].size_bytes == 6
    assert cards[1].sha256 == hashlib.sha256(b"frames").hexdigest()


def test_logs_come_first_and_big_non_logs_stay_behind():
    """
    The script's log, then the command's output, then other text; a
    long log still goes (as its end), a big structure does not, and
    nothing in a subfolder does.
    """
    big = UI_FILE_MAX_BYTES + 1
    cards = [
        card("result.xyz"),
        card("huge_traj.xyz", big),
        card("execution.log"),
        card("xtb_md.log", big),
        card("md/inner.log"),
        card("frames.trj"),
        card("other.log"),
    ]

    assert pick_ui_files(cards, "xtb_md") == [
        "xtb_md.log",
        "execution.log",
        "other.log",
        "result.xyz",
    ]


def test_at_most_the_limit_of_ui_files_is_chosen():
    """
    A folder of many small text files sends only ``MAX_UI_FILES``.
    """
    cards = [card(f"frame_{index:03}.xyz") for index in range(50)]
    assert len(pick_ui_files(cards, "task")) == MAX_UI_FILES


def test_a_long_log_is_sent_as_its_end(tmp_path: Path):
    """
    Only the last ``max_bytes`` of a long file are uploaded.

    :param tmp_path: A job folder.
    :type tmp_path: Path
    """
    log = tmp_path / "md.log"
    log.write_bytes(b"start" + b"x" * 100 + b"END")
    assert upload_body(log, max_bytes=3) == b"END"
    assert upload_body(log, max_bytes=1000) == log.read_bytes()
