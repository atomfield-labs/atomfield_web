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

CommandLine = Callable[..., int]


def stops_cleanly(message: str) -> Callable[[CommandLine], CommandLine]:
    """
    Make a command-line function end quietly when the person stops it:
    ``@stops_cleanly("Stopped; nothing was saved.")``.

    :param message: What to say then: what was, or was not, done.
    :type message: str
    :return: The decorator.
    :rtype: Callable[[CommandLine], CommandLine]
    """
    return functools.partial(with_clean_stop, message)


def with_clean_stop(message: str, main: CommandLine) -> CommandLine:
    """
    Wrap one command-line function: on Ctrl+C or Ctrl+D it says
    ``message`` and returns ``EXIT_INTERRUPTED``.

    :param message: What to say when stopped.
    :type message: str
    :param main: Returns the program's exit code.
    :type main: CommandLine
    :return: The same function, stopping cleanly.
    :rtype: CommandLine
    """

    @functools.wraps(main)
    def run(*args: Any, **kwargs: Any) -> int:
        """
        :return: The command's exit code, or ``EXIT_INTERRUPTED``.
        :rtype: int
        """
        try:
            return main(*args, **kwargs)
        except (KeyboardInterrupt, EOFError):
            # A new line first: the terminal still shows the question,
            # or ^C.
            print(f"\n{message}", file=sys.stderr)
            return EXIT_INTERRUPTED

    return run
