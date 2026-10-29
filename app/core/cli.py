"""
How AtomField's command-line programs end when a person stops them.

Ctrl+C, or Ctrl+D at a question, means "stop", not "crash": the
program says what that leaves undone and exits with the code shells
use for an interrupted program, instead of printing a traceback.

The agent uses this on clusters, so it imports nothing beyond the
standard library.
"""

import functools
import sys
from collections.abc import Callable
from typing import Any

# What shells report for a program stopped by Ctrl+C (128 + SIGINT).
EXIT_INTERRUPTED = 130


def stops_cleanly(
    message: str,
) -> Callable[[Callable[..., int]], Callable[..., int]]:
    """
    Make a command-line function end quietly when the person stops it.

    :param message: What to say then: what was, or was not, done.
    :type message: str
    :return: The decorator.
    :rtype: Callable[[Callable[..., int]], Callable[..., int]]
    """

    def decorate(main: Callable[..., int]) -> Callable[..., int]:
        """
        Wrap one command-line function.

        :param main: Returns the program's exit code.
        :type main: Callable[..., int]
        :return: The same function, stopping cleanly.
        :rtype: Callable[..., int]
        """

        @functools.wraps(main)
        def run(*args: Any, **kwargs: Any) -> int:
            """
            Run it; on Ctrl+C or Ctrl+D, say ``message`` instead.

            :return: Its exit code, or ``EXIT_INTERRUPTED``.
            :rtype: int
            """
            try:
                return main(*args, **kwargs)
            except (KeyboardInterrupt, EOFError):
                # A new line first: the terminal still shows the
                # question, or ^C.
                print(f"\n{message}", file=sys.stderr)
                return EXIT_INTERRUPTED

        return run

    return decorate
