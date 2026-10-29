"""
Names: which file and folder names are plain (one name that cannot
point anywhere else), and how a published name and version is shown.

Kept free of server imports: the server's file store, its submission
checks and the agent's job folders all judge names by this one rule.
"""

from collections import Counter
from collections.abc import Iterable

UNSAFE_NAMES = frozenset({"", ".", ".."})
SEPARATORS = ("/", "\\")
# Characters below this one are control characters (newline, tab...).
FIRST_PRINTABLE = " "


def is_plain_name(name: str) -> bool:
    """
    Whether a name is one plain file or folder name: not empty, ``.``
    or ``..``, without a separator (``/``, ``\\``) or a control
    character.

    :param name: Proposed name.
    :type name: str
    :return: True if it names one entry directly inside a folder.
    :rtype: bool
    """
    if name in UNSAFE_NAMES:
        return False
    if any(separator in name for separator in SEPARATORS):
        return False
    return all(char >= FIRST_PRINTABLE for char in name)


def version_label(name: str, version: str) -> str:
    """
    How people see a published name and version (a release, a data
    pack): ``afscripts 0.2.0``.

    :param name: The name.
    :type name: str
    :param version: The version.
    :type version: str
    :return: The label.
    :rtype: str
    """
    return f"{name} {version}"


def given_twice(names: Iterable[str]) -> list[str]:
    """
    The names that appear more than once, for refusing a list that
    must name each thing once (task ids, flags, pipeline nodes).

    :param names: The names, as given.
    :type names: Iterable[str]
    :return: Each repeated name once, sorted.
    :rtype: list[str]
    """
    return sorted(name for name, count in Counter(names).items() if count > 1)
