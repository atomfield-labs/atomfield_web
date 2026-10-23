"""
The agent's memory across restarts: which process groups it started.

If the agent dies, its jobs' processes keep running (they are in their
own process groups). On the next start the agent stops those orphans;
the server, seeing no heartbeat, retries the jobs on a new attempt.
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

    def load(self) -> dict[str, dict[str, int]]:
        """
        Read the recorded jobs; a missing or broken file means none.

        :return: Job id -> {"attempt": n, "process_group": pgid}.
        :rtype: dict[str, dict[str, int]]
        """
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))[JOBS_KEY]
        except (OSError, ValueError, KeyError):
            return {}

    def save(self, jobs: dict[str, dict[str, int]]) -> None:
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

    def record(self, job_id: str, attempt: int, process_group: int) -> None:
        """
        Remember a started job.

        :param job_id: Job id.
        :type job_id: str
        :param attempt: Attempt number.
        :type attempt: int
        :param process_group: Its process group.
        :type process_group: int
        """
        jobs = self.load()
        jobs[job_id] = {"attempt": attempt, "process_group": process_group}
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
