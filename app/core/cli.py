"""
How AtomField's command-line programs end: with their result, with
one line saying what went wrong, or when a person stops them.

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

EXIT_OK = 0
EXIT_FAILED = 1
# What shells report for a program stopped by Ctrl+C (128 + SIGINT).
EXIT_INTERRUPTED = 130

CommandLine = Callable[..., int]


def fail(message: object) -> int:
    """
    Say what went wrong in one line, and give the exit code for it.

    :param message: What went wrong (an exception says it itself).
    :type message: object
    :return: ``EXIT_FAILED``.
    :rtype: int
    """
    print(f"Error: {message}", file=sys.stderr)
    return EXIT_FAILED


def print_outcome(
    action: Callable[[], str], errors: tuple[type[Exception], ...]
) -> int:
    """
    Run a command's work and print the line it returns; an expected
    error is printed as one line instead of a traceback.

    :param action: The work; returns what happened, for the person.
    :type action: Callable[[], str]
    :param errors: The failures whose message says it all.
    :type errors: tuple[type[Exception], ...]
    :return: ``EXIT_OK``, or ``EXIT_FAILED`` after such an error.
    :rtype: int
    """
    try:
        print(action())
    except errors as error:
        return fail(error)
    return EXIT_OK


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
