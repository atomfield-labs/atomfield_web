"""
End-to-end checks of live updates against a running stack: every
change arrives on the stream, numbered and promptly; a watcher that
comes back starts from the current state; and a watcher connected to
another API process sees the same changes. Run with ``pytest -m e2e``.
"""

import json
import os
import time
from collections.abc import Iterator

import pytest
import requests

from tests.e2e.test_pipeline_execution import (
    BASE_URL,
    build_chain,
    fetch_job,
    runner_headers,
    task_node,
)

pytestmark = pytest.mark.e2e

# A second API process sharing the database and Redis, if one runs.
SECOND_URL = os.environ.get("ATOMFIELD_E2E_URL_2")
FINAL = {"succeeded", "failed", "upstream_failed", "cancelled"}
# Longest silence on a stream: pings come every 15 seconds.
READ_TIMEOUT_SECONDS = 20
# Everything around a job (claim, report, commit, publish, stream).
OVERHEAD_BUDGET_SECONDS = 1.0
FINISH_TIMEOUT_SECONDS = 60

Frame = tuple[float, str, dict]


@pytest.fixture(scope="module")
def headers() -> dict[str, str]:
    """
    The person the module's tests run as.

    :return: Headers carrying their key.
    :rtype: dict[str, str]
    """
    return runner_headers()


def submit_run(headers: dict[str, str]) -> dict:
    """
    Submit ``opt -> md`` on water.

    :param headers: User headers.
    :type headers: dict[str, str]
    :return: Submission receipt (``job_ids``, ``run_id``).
    :rtype: dict
    """
    nodes = [task_node("opt", "xtb_opt"), task_node("md", "xtb_md", time=2.0)]
    response = requests.post(
        f"{BASE_URL}/api/jobs/pipeline/submit",
        json=build_chain(nodes, with_water=True),
        headers=headers,
    )
    assert response.status_code == 202
    return response.json()


def frames(base_url: str, run_id: str, headers: dict) -> Iterator[Frame]:
    """
    Yield each frame of a run's stream with its arrival time; closing
    the iterator disconnects.

    :param base_url: API process to connect to.
    :type base_url: str
    :param run_id: Run to watch.
    :type run_id: str
    :param headers: User headers.
    :type headers: dict
    :return: (arrival time, frame type, data) per frame.
    :rtype: Iterator[Frame]
    """
    url = f"{base_url}/api/runs/{run_id}/events"
    timeout = (5, READ_TIMEOUT_SECONDS)
    with requests.get(
        url, headers=headers, stream=True, timeout=timeout
    ) as response:
        assert response.status_code == 200
        lines = []
        for line in response.iter_lines(decode_unicode=True):
            if line:
                lines.append(line)
                continue
            kind = lines[0].removeprefix("event: ")
            data = json.loads(lines[1].removeprefix("data: "))
            lines = []
            yield time.monotonic(), kind, data


def watch_until_finished(base_url: str, run_id: str, headers: dict) -> list:
    """
    Read a run's stream until every job is final.

    :param base_url: API process to connect to.
    :type base_url: str
    :param run_id: Run to watch.
    :type run_id: str
    :param headers: User headers.
    :type headers: dict
    :return: Every frame received.
    :rtype: list[Frame]
    """
    seen, statuses = [], {}
    for arrival, kind, data in frames(base_url, run_id, headers):
        seen.append((arrival, kind, data))
        if kind == "snapshot":
            statuses = {job["job_id"]: job["status"] for job in data["jobs"]}
        elif kind == "job":
            statuses[data["job_id"]] = data["status"]
        if statuses and set(statuses.values()) <= FINAL:
            return seen
    raise AssertionError("stream ended before the run finished")


def job_events(seen: list) -> list[dict]:
    """
    Keep the job events of a stream, in arrival order.

    :param seen: Frames received.
    :type seen: list[Frame]
    :return: Job event data.
    :rtype: list[dict]
    """
    return [data for _, kind, data in seen if kind == "job"]


def test_every_change_arrives_numbered_and_promptly(headers: dict):
    """
    After the snapshot every change arrives once, numbered without
    gaps; and md's two events bracket its real run time with less than
    a second of overhead.

    :param headers: User headers.
    :type headers: dict
    """
    run = submit_run(headers)
    seen = watch_until_finished(BASE_URL, run["run_id"], headers)

    (_, kind, snapshot), *rest = seen
    assert kind == "snapshot"
    numbers = [event["seq"] for event in job_events(rest)]
    first = snapshot["seq"] + 1
    assert numbers == list(range(first, first + len(numbers)))

    md = run["job_ids"]["md"]
    arrived = {
        data["status"]: arrival
        for arrival, kind, data in rest
        if kind == "job" and data["job_id"] == md
    }
    assert {"running", "succeeded"} <= arrived.keys(), arrived
    ran = fetch_job(md, headers)["execution_time_seconds"]
    overhead = arrived["succeeded"] - arrived["running"] - ran
    assert overhead < OVERHEAD_BUDGET_SECONDS


def test_a_returning_watcher_starts_from_the_current_state(headers: dict):
    """
    A watcher that leaves and comes back after the run finished gets a
    snapshot with the final states and a higher count.

    :param headers: User headers.
    :type headers: dict
    """
    run = submit_run(headers)
    stream = frames(BASE_URL, run["run_id"], headers)
    _, _, before = next(stream)
    stream.close()

    give_up_at = time.monotonic() + FINISH_TIMEOUT_SECONDS
    md = run["job_ids"]["md"]
    while fetch_job(md, headers)["status"] not in FINAL:
        assert time.monotonic() < give_up_at, "run did not finish"
        time.sleep(0.5)

    _, kind, after = next(frames(BASE_URL, run["run_id"], headers))
    assert kind == "snapshot"
    assert {job["status"] for job in after["jobs"]} == {"succeeded"}
    assert after["seq"] > before["seq"]


@pytest.mark.skipif(
    SECOND_URL is None,
    reason="needs ATOMFIELD_E2E_URL_2: a second API process",
)
def test_a_watcher_on_another_api_process_sees_each_change(headers: dict):
    """
    The run is submitted to, and reported to, the first API process;
    a watcher connected to the second still receives the events,
    through Redis, as they happen (not only at the next ping).

    :param headers: User headers.
    :type headers: dict
    """
    run = submit_run(headers)
    seen = watch_until_finished(SECOND_URL, run["run_id"], headers)

    events = job_events(seen)
    assert events, "only snapshots arrived: events did not cross"
    assert events[-1]["status"] == "succeeded"
