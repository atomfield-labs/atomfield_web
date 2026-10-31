"""
What the publish commands share: the error they stop with, and how
they run another program.
"""

import subprocess


class PublishError(RuntimeError):
    """
    A step of publishing failed; the message says which and why.
    """


def run_tool(argv: list[str]) -> str:
    """
    Run a command and return its output.

    :param argv: The command.
    :type argv: list[str]
    :return: Its standard output.
    :rtype: str
    :raises PublishError: If it fails or cannot be found.
    """
    try:
        done = subprocess.run(argv, capture_output=True, text=True, check=True)
    except FileNotFoundError as error:
        raise PublishError(f"{argv[0]} is not installed") from error
    except subprocess.CalledProcessError as error:
        raise PublishError(
            f"{' '.join(argv)} failed:\n{error.stderr}"
        ) from error
    return done.stdout
