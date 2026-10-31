"""
The kinds of computer scripts are built for.

Kept free of server imports, so the agent, which runs on machines
without the API's dependencies, names its machine as the API expects.
"""

import platform
import sys

# A wheel for every package or every machine: what was published before
# compiled packages, and tests' plain releases.
ANY = "any"
MACHINE_LENGTH = 32


def this_machine() -> str:
    """
    The kind of computer this is, which decides the build it can run.

    :return: e.g. ``linux-x86_64`` or ``darwin-arm64``.
    :rtype: str
    """
    return f"{sys.platform}-{platform.machine().lower()}"
