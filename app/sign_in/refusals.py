"""
Why a sign-in was refused, in the words the web app is told.
"""

from enum import StrEnum


class SignInProblem(StrEnum):
    """
    What went wrong, sent back to the web app as ``?sign_in_error=``.
    """

    # Took too long, was already used, or began in another browser.
    EXPIRED = "expired"
    # The person said no at the provider.
    DENIED = "denied"
    # Not an account of an allowed institute.
    OUTSIDE = "outside"
    # The administrator has turned the account off.
    DISABLED = "disabled"
    # The provider's answer did not check out.
    FAILED = "failed"
    # This server has no sign-in set up.
    UNAVAILABLE = "unavailable"
    # Too many sign-ins started from one address; wait a minute.
    BUSY = "busy"


class SignInRefused(Exception):
    """
    A sign-in that must not go ahead.
    """

    def __init__(self, problem: SignInProblem) -> None:
        """
        Say why.

        :param problem: What went wrong.
        :type problem: SignInProblem
        """
        super().__init__(problem.value)
        self.problem = problem
