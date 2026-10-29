"""
The message a watcher receives when a job changes.
"""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.runs.states import JobStatus


def state_fields(job: Any) -> dict[str, Any]:
    """
    A job's state as events and snapshots carry it.

    :param job: A Job, or a row with the same columns.
    :type job: Any
    :return: ``job_id``, ``status``, ``attempt``, ``error_message``,
        ``started``.
    :rtype: dict[str, Any]
    """
    return {
        "job_id": job.id,
        "status": JobStatus(job.status),
        "attempt": job.attempt,
        "error_message": job.error_message,
        "started": job.started_at is not None,
    }


class JobEvent(BaseModel):
    """
    One job's new state, numbered within its run.

    An event carries state ("B is now queued"), never a step ("move B
    on"), so applying it twice changes nothing. ``seq`` comes from the
    run's counter: a watcher already showing a higher number for this
    job knows the event is old and ignores it.
    """

    # Pydantic rather than a dataclass: events travel through Redis as
    # JSON, and model_validate_json checks what comes back in.
    model_config = ConfigDict(frozen=True)

    run_id: uuid.UUID
    seq: int
    job_id: uuid.UUID
    status: JobStatus
    attempt: int
    error_message: str | None = None
    # Running in name only until a scheduler actually starts it.
    started: bool = False


class JobState(BaseModel):
    """
    One job's current state, as part of a snapshot.
    """

    job_id: uuid.UUID
    status: JobStatus
    attempt: int
    error_message: str | None = None
    started: bool = False


class RunSnapshot(BaseModel):
    """
    Every job of a run plus the run's counter, read at one moment.

    A watcher shows these states, then applies only events numbered
    above ``seq``; anything at or below it is already included.
    """

    run_id: uuid.UUID
    seq: int
    jobs: list[JobState]
