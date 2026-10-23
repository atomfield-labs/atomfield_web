"""
Turn how a command ended into the report the server records.

Pure functions: no I/O, so every outcome is easy to test on its own.
"""

import traceback
from enum import StrEnum
from pathlib import Path

from agent.workspace import failure_message, success_output
from app.agents.schemas import CompletionRequest, JobAssignment


class StopReason(StrEnum):
    """
    Why the agent stopped a job before it finished by itself.
    """

    CANCELLED = "cancelled"  # the user asked; report it
    ABANDONED = "abandoned"  # no longer ours; report nothing
    TIMEOUT = "timeout"  # ran past its deadline; report a failure


def stopped_report(
    assignment: JobAssignment,
    reason: StopReason,
    duration: float,
) -> CompletionRequest | None:
    """
    Report for a job the agent stopped itself.

    :param assignment: The attempt that was stopped.
    :type assignment: JobAssignment
    :param reason: Why it was stopped.
    :type reason: StopReason
    :param duration: Seconds it ran.
    :type duration: float
    :return: The report, or None for an abandoned job.
    :rtype: CompletionRequest | None
    """
    if reason is StopReason.ABANDONED:
        return None
    if reason is StopReason.CANCELLED:
        outcome, message = "cancelled", "Cancelled by request"
    else:
        limit = assignment.task.resources.walltime_minutes
        outcome = "failed"
        message = f"{assignment.task.id} exceeded its {limit}-minute limit"
    return CompletionRequest(
        attempt=assignment.attempt,
        outcome=outcome,
        error_message=message,
        execution_time_seconds=duration,
    )


def exit_report(
    assignment: JobAssignment,
    return_code: int,
    workspace: Path,
    pipeline_id: str,
    duration: float,
) -> CompletionRequest:
    """
    Report for a job that ended by itself.

    :param assignment: The attempt that ran.
    :type assignment: JobAssignment
    :param return_code: Its exit code.
    :type return_code: int
    :param workspace: Its workspace.
    :type workspace: Path
    :param pipeline_id: Its pipeline.
    :type pipeline_id: str
    :param duration: Seconds it ran.
    :type duration: float
    :return: Success with the file list, or failure with the log tail.
    :rtype: CompletionRequest
    """
    task_id, job_id = assignment.task.id, str(assignment.job_id)
    common = {"attempt": assignment.attempt, "execution_time_seconds": duration}
    if return_code == 0:
        output = success_output(task_id, workspace, pipeline_id, job_id)
        return CompletionRequest(
            outcome="succeeded", output_data=output, **common
        )
    message = failure_message(task_id, workspace, return_code)
    return CompletionRequest(outcome="failed", error_message=message, **common)


def crash_report(
    assignment: JobAssignment, error: Exception
) -> CompletionRequest:
    """
    Report for a job the agent itself failed to run (bad workspace,
    missing interpreter, ...). Call from an ``except`` block.

    :param assignment: The attempt that crashed.
    :type assignment: JobAssignment
    :param error: What went wrong.
    :type error: Exception
    :return: A failure carrying the traceback.
    :rtype: CompletionRequest
    """
    message = f"{type(error).__name__}: {error}\n{traceback.format_exc()}"
    return CompletionRequest(
        attempt=assignment.attempt, outcome="failed", error_message=message
    )
