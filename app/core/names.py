"""
Plain names: one file or folder name that cannot point anywhere else.

Kept free of server imports: the server's file store, its submission
checks and the agent's job folders all judge names by this one rule.
"""

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
