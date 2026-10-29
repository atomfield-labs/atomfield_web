"""
Job states and the one table of moves allowed between them.

Every status string in the platform comes from ``JobStatus``, and every
change goes through ``ALLOWED_SOURCES``, so an impossible move (a
finished job starting again, say) cannot be written by any code path.
"""

from enum import StrEnum
from types import MappingProxyType

# What a job cancelled by its owner says; the agent says it too, for
# a running job it stopped on request.
CANCELLED_MESSAGE = "Cancelled by request"


class JobStatus(StrEnum):
    """
    Where a job is in its life.
    """

    WAITING = "waiting"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UPSTREAM_FAILED = "upstream_failed"


FINAL_STATUSES = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.UPSTREAM_FAILED,
    }
)

# Counted as failures in statistics.
FAILURE_STATUSES = frozenset({JobStatus.FAILED, JobStatus.UPSTREAM_FAILED})

# A parent in one of these means its children can never run.
UNSUCCESSFUL_STATUSES = FAILURE_STATUSES | {JobStatus.CANCELLED}

# Not started yet: cancelling one needs no agent.
NOT_STARTED_STATUSES = frozenset({JobStatus.WAITING, JobStatus.QUEUED})

# Target status -> the statuses a job may move into it from. Read it as
# "a job becomes QUEUED only from WAITING (its parents are done) or from
# RUNNING (its agent was lost and it is retried)".
ALLOWED_SOURCES = MappingProxyType(
    {
        JobStatus.QUEUED: frozenset({JobStatus.WAITING, JobStatus.RUNNING}),
        JobStatus.RUNNING: frozenset({JobStatus.QUEUED}),
        JobStatus.SUCCEEDED: frozenset({JobStatus.RUNNING}),
        JobStatus.FAILED: frozenset({JobStatus.QUEUED, JobStatus.RUNNING}),
        JobStatus.CANCELLED: frozenset(
            {JobStatus.WAITING, JobStatus.QUEUED, JobStatus.RUNNING}
        ),
        JobStatus.UPSTREAM_FAILED: frozenset({JobStatus.WAITING}),
    }
)


def can_move(source: JobStatus, target: JobStatus) -> bool:
    """
    Check one move against the table.

    :param source: Current status.
    :type source: JobStatus
    :param target: Wanted status.
    :type target: JobStatus
    :return: True if the move is allowed.
    :rtype: bool
    """
    return source in ALLOWED_SOURCES.get(target, frozenset())
