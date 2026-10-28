"""
The agent's memory across restarts: which jobs it started, how to find
each again (its handle: a process group, a Slurm job id), and the
whole assignment.

On the next start the runner decides: a local orphan is stopped (its
parent is gone; the server retries the job), a Slurm job is taken
over (Slurm kept it running; the new agent watches and reports it).
"""

import json
import os
from pathlib import Path

JOBS_KEY = "jobs"


class StateFile:
    """
    A small JSON file mapping job id -> attempt and process group.
    """

    def __init__(self, path: Path) -> None:
        """
        Use (or later create) the file at ``path``.

        :param path: State file location.
        :type path: Path
        """
        self.path = path

    def load(self) -> dict[str, dict]:
        """
        Read the recorded jobs; a missing or broken file means none.

        :return: Job id -> {"attempt": n, "process_group": pgid}.
        :rtype: dict[str, dict[str, int]]
        """
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))[JOBS_KEY]
        except (OSError, ValueError, KeyError):
            return {}

    def save(self, jobs: dict[str, dict]) -> None:
        """
        Write the recorded jobs atomically.

        The write goes to a temporary file that is then renamed over
        the real one; a rename is atomic, so a crash mid-write can never
        leave half a file behind.

        :param jobs: Job id -> {"attempt": n, "process_group": pgid}.
        :type jobs: dict[str, dict[str, int]]
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({JOBS_KEY: jobs}), encoding="utf-8")
        os.replace(temporary, self.path)

    def record(
        self,
        job_id: str,
        attempt: int,
        handle: str,
        assignment: dict | None = None,
    ) -> None:
        """
        Remember a started job.

        :param job_id: Job id.
        :type job_id: str
        :param attempt: Attempt number.
        :type attempt: int
        :param handle: How the runner finds the job again.
        :type handle: str
        :param assignment: The assignment as JSON, so a new agent can
            take the job over.
        :type assignment: dict | None
        """
        jobs = self.load()
        jobs[job_id] = {
            "attempt": attempt,
            "handle": handle,
            "assignment": assignment,
        }
        self.save(jobs)

    def forget(self, job_id: str) -> None:
        """
        Drop a job that has ended.

        :param job_id: Job id.
        :type job_id: str
        """
        jobs = self.load()
        jobs.pop(job_id, None)
        self.save(jobs)
