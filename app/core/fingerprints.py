"""
Fingerprints: the sha256 that identifies every release, data pack and
result file, checked on both ends of each transfer.

Kept free of server imports, for the agent.
"""

import hashlib
from pathlib import Path


def file_sha256(path: Path) -> str:
    """
    A file's fingerprint, read in pieces, so a big file never has to
    fit in memory.

    :param path: The file.
    :type path: Path
    :return: Its sha256, in hex.
    :rtype: str
    """
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, hashlib.sha256).hexdigest()
