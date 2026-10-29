"""
The sweeper repairs what the happy path missed, without ever undoing
an agent's progress; cancellation works for queued and running jobs.
"""

import asyncio
import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.events.bus import InMemoryEventBus
from app.main import create_store
from app.models.compute_target import HOUSE_TARGET_ID
from app.models.job import Job
from app.queue.job_queue import RedisJobQueue, queue_key
from app.runs.lifecycle import SilenceLimits, requeue_lost, start_attempt
from app.runs.states import JobStatus
from app.scheduler.sweeper import Sweeper
from tests.graphs import build_graph, commit_changes, snapshot
from tests.stores import make_redis

UserHeadersFactory = Callable[..., dict[str, str]]
LONG_AGO = timedelta(minutes=10)
LIMITS = SilenceLimits(
    local=timedelta(minutes=3), scheduled=timedelta(hours=24)
)


def with_sweeper(make_session: async_sessionmaker, scenario):
    """
    Run an async scenario with a sweeper on fresh connections.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param scenario: Coroutine function taking (sweeper, redis).
    :type scenario: Callable
    :return: Whatever the scenario returns.
    :rtype: Any
    """

    async def wrapper():
        redis = make_redis()
        store = create_store()
        sweeper = Sweeper(
            make_session,
            RedisJobQueue(redis),
            InMemoryEventBus(),
            redis,
            store,
            interval_seconds=30,
            limits=LIMITS,
            deadline_grace=timedelta(minutes=10),
        )
        try:
            return await scenario(sweeper, redis)
        finally:
            await redis.aclose()

    return asyncio.run(wrapper())


async def is_queued_in_redis(redis, job_id: uuid.UUID) -> bool:
    """
    Check whether a job id sits in the house agent's queue.

    :param redis: Redis client.
    :type redis: Redis
    :param job_id: Job to look for.
    :type job_id: uuid.UUID
    :return: True if queued in Redis.
    :rtype: bool
    """
    score = await redis.zscore(queue_key(HOUSE_TARGET_ID), str(job_id))
    return score is not None


async def start_running(make_session, job_id, **values) -> None:
    """
    Start a job's attempt, then set extra columns (e.g. an old
    heartbeat) to simulate time passing.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param job_id: Job to start.
    :type job_id: uuid.UUID
    :param values: Columns to overwrite after starting.
    :type values: Any
    """
    async with make_session() as session:
        await start_attempt(session, job_id, 10, agent_id=HOUSE_TARGET_ID)
        if values:
            await session.execute(
                update(Job).where(Job.id == job_id).values(**values)
            )
        await commit_changes(session)


async def read(make_session, ids) -> dict[str, tuple[str, int]]:
    """
    Snapshot job states in a fresh session.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param ids: Job name -> id.
    :type ids: dict[str, uuid.UUID]
    :return: Name -> (status, pending_parents).
    :rtype: dict[str, tuple[str, int]]
    """
    async with make_session() as session:
        return await snapshot(session, ids)


def test_a_job_saved_but_never_sent_is_delivered(make_session):
    """
    Fault test 1: a crash between commit and dispatch leaves a queued
    job Redis never heard of; the next pass sends it.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
        before = await is_queued_in_redis(redis, ids["A"])
        await sweeper.sweep_once()
        return before, await is_queued_in_redis(redis, ids["A"])

    assert with_sweeper(make_session, scenario) == (False, True)


def test_the_queue_refills_after_redis_is_wiped(make_session):
    """
    Fault test 5: Redis loses everything; Postgres still knows which
    jobs are queued, so the next pass puts them back.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
        await sweeper.sweep_once()
        await redis.flushdb()
        await sweeper.sweep_once()
        return await is_queued_in_redis(redis, ids["A"])

    assert with_sweeper(make_session, scenario) is True


def test_a_silent_agent_gets_one_retry_then_failure(make_session):
    """
    Fault test 4: attempt 1's agent goes silent, so the job is queued
    again; attempt 2's agent goes silent too, so it fails and its child
    can never run.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    stale = {"last_heartbeat_at": func.now() - LONG_AGO}

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
        await start_running(make_session, ids["A"], **stale)
        first = await sweeper.sweep_once()
        after_first = (await read(make_session, ids))["A"]
        requeued = await is_queued_in_redis(redis, ids["A"])
        await start_running(make_session, ids["A"], **stale)
        second = await sweeper.sweep_once()
        return (
            first,
            after_first,
            requeued,
            second,
            await read(make_session, ids),
        )

    first, after_first, requeued, second, final = with_sweeper(
        make_session, scenario
    )
    assert first.retried >= 1 and after_first[0] == JobStatus.QUEUED
    assert requeued
    assert second.failed >= 1
    assert final["A"][0] == JobStatus.FAILED
    assert final["B"][0] == JobStatus.UPSTREAM_FAILED


def test_a_live_job_is_never_touched(make_session):
    """
    A fresh heartbeat means the agent is alive: the sweeper leaves the
    job alone however long it has been running.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
        await start_running(make_session, ids["A"])
        await sweeper.sweep_once()
        return await read(make_session, ids)

    state = with_sweeper(make_session, scenario)
    assert state["A"][0] == JobStatus.RUNNING


def test_a_cancel_reaches_a_job_whose_agent_is_gone(make_session):
    """
    Fault test 8: a cancel requested while the agent is offline still
    completes, and the job's children are cancelled with it.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
        await start_running(
            make_session,
            ids["A"],
            cancel_requested=True,
            last_heartbeat_at=func.now() - LONG_AGO,
        )
        await sweeper.sweep_once()
        return await read(make_session, ids)

    state = with_sweeper(make_session, scenario)
    assert state["A"][0] == JobStatus.CANCELLED
    assert state["B"][0] == JobStatus.CANCELLED


def test_a_job_long_past_its_deadline_fails(make_session):
    """
    Even with a live agent, a job far past its deadline is failed (and
    not retried: it would run out of time again).

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
        await start_running(
            make_session, ids["A"], deadline_at=func.now() - timedelta(hours=1)
        )
        await sweeper.sweep_once()
        return await read(make_session, ids)

    state = with_sweeper(make_session, scenario)
    assert state["A"][0] == JobStatus.FAILED
    assert state["B"][0] == JobStatus.UPSTREAM_FAILED


def test_only_one_process_sweeps_per_round(make_session):
    """
    Two sweepers racing for the same round: exactly one gets the lock.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(sweeper, redis):
        await redis.delete("sweeper:lock")
        return await asyncio.gather(
            sweeper.acquire_round(), sweeper.acquire_round()
        )

    assert sorted(with_sweeper(make_session, scenario)) == [False, True]


@pytest.fixture
def pipeline(client: TestClient, make_user_headers: UserHeadersFactory):
    """
    A submitted two-job chain: (owner headers, run id, [first, second]).

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :return: Owner headers, run id and job ids.
    :rtype: tuple[dict[str, str], str, list[str]]
    """
    headers = make_user_headers()
    payload = {
        "nodes": [
            {"ui_id": "first", "script_name": "toy_opt"},
            {"ui_id": "second", "script_name": "toy_opt"},
        ],
        "edges": [{"upstream_ui_id": "first", "downstream_ui_id": "second"}],
    }
    body = client.post(
        "/api/jobs/pipeline/submit", json=payload, headers=headers
    ).json()
    return (
        headers,
        body["run_id"],
        [body["job_ids"]["first"], body["job_ids"]["second"]],
    )


def test_cancelling_a_queued_job_is_immediate(client: TestClient, pipeline):
    """
    A job that has not started is cancelled at once, with its child;
    cancelling it again is a conflict.

    :param client: In-process API client.
    :type client: TestClient
    :param pipeline: Owner headers, run id and job ids.
    :type pipeline: tuple
    """
    headers, _, (first, second) = pipeline
    response = client.post(f"/api/jobs/{first}/cancel", headers=headers)
    assert response.json()["status"] == "cancelled"
    child = client.get(f"/api/jobs/{second}", headers=headers).json()
    assert child["status"] == "cancelled"
    again = client.post(f"/api/jobs/{first}/cancel", headers=headers)
    assert again.status_code == 409


def test_cancelling_a_run_asks_running_jobs_to_stop(
    client: TestClient,
    pipeline,
    make_session: async_sessionmaker,
):
    """
    Cancelling a run: the running job is flagged (its agent stops it),
    the waiting one is cancelled at once.

    :param client: In-process API client.
    :type client: TestClient
    :param pipeline: Owner headers, run id and job ids.
    :type pipeline: tuple
    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    headers, run_id, (first, _) = pipeline
    asyncio.run(start_running(make_session, uuid.UUID(first)))

    response = client.post(f"/api/runs/{run_id}/cancel", headers=headers)

    assert response.json() == {
        "run_id": run_id,
        "cancelled": 1,
        "cancelling": 1,
    }
    stranger = client.post(f"/api/runs/{run_id}/cancel")
    assert stranger.status_code == 401


def test_a_heartbeat_just_before_the_requeue_wins(make_session):
    """
    The sweeper read the job as lost, but the agent reported in before
    the write: the re-check inside the UPDATE keeps the job running.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
        await start_running(make_session, ids["A"])  # fresh heartbeat
        async with make_session() as session:
            moved = await requeue_lost(session, ids["A"], 1, LIMITS)
            await commit_changes(session)
        return moved, await read(make_session, ids)

    moved, state = with_sweeper(make_session, scenario)
    assert moved is None
    assert state["A"][0] == JobStatus.RUNNING


def test_a_job_waiting_in_a_cluster_queue_is_never_overdue(make_session):
    """
    A job a scheduled agent claimed long ago but Slurm has not started
    has no deadline yet, so the sweeper leaves it alone.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            await start_attempt(
                session, ids["A"], 1, agent_id=HOUSE_TARGET_ID, scheduled=True
            )
            await session.execute(
                update(Job)
                .where(Job.id == ids["A"])
                .values(last_heartbeat_at=func.now())
            )
            await commit_changes(session)
        report = await sweeper.sweep_once()
        return report.overdue, (await read(make_session, ids))["A"][0]

    assert with_sweeper(make_session, scenario) == (0, JobStatus.RUNNING)


def test_a_silent_cluster_agent_gets_a_day_before_its_jobs_are_retried(
    make_session,
):
    """
    A Slurm job keeps running while its agent is down, so two hours of
    silence change nothing; only after a full day is it queued again.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def silent_for(job_id, silence: timedelta) -> None:
        async with make_session() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(last_heartbeat_at=func.now() - silence)
            )
            await session.commit()

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            await start_attempt(
                session, ids["A"], 10, agent_id=HOUSE_TARGET_ID, scheduled=True
            )
            await commit_changes(session)
        await silent_for(ids["A"], timedelta(hours=2))
        after_two_hours = (await sweeper.sweep_once()).retried
        state_then = (await read(make_session, ids))["A"][0]
        await silent_for(ids["A"], timedelta(hours=25))
        after_a_day = (await sweeper.sweep_once()).retried
        state_now = (await read(make_session, ids))["A"][0]
        return after_two_hours, state_then, after_a_day, state_now

    assert with_sweeper(make_session, scenario) == (
        0,
        JobStatus.RUNNING,
        1,
        JobStatus.QUEUED,
    )


def test_a_requeued_job_keeps_nothing_of_its_lost_attempt(make_session):
    """
    Back in the queue, a lost job has no agent, lease, start time or
    deadline left from the attempt that was lost.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    stale = {"last_heartbeat_at": func.now() - LONG_AGO}

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
        await start_running(make_session, ids["A"], **stale)
        await sweeper.sweep_once()
        async with make_session() as session:
            return await session.get(Job, ids["A"])

    job = with_sweeper(make_session, scenario)
    assert job.status == JobStatus.QUEUED
    left = (job.agent_id, job.last_heartbeat_at, job.started_at)
    assert left == (None, None, None)
    assert job.deadline_at is None


def test_cancelling_a_waiting_job_ends_it_and_nothing_upstream(
    client: TestClient, pipeline
):
    """
    A job still waiting for its parent is cancelled at once; its parent
    is not touched.

    :param client: In-process API client.
    :type client: TestClient
    :param pipeline: Owner headers, run id and job ids.
    :type pipeline: tuple
    """
    headers, _, (first, second) = pipeline
    response = client.post(f"/api/jobs/{second}/cancel", headers=headers)
    assert response.json()["status"] == "cancelled"
    parent = client.get(f"/api/jobs/{first}", headers=headers).json()
    assert parent["status"] == "queued"


def test_cancelling_a_run_counts_every_job_it_cancelled(
    client: TestClient, make_user_headers: UserHeadersFactory
):
    """
    A run of three jobs that have not started reports three cancelled,
    whatever order the jobs are found in (cancelling the first one used
    to take the others along uncounted).

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers()
    nodes = [{"ui_id": name, "script_name": "toy_opt"} for name in "abc"]
    edges = [
        {"upstream_ui_id": "a", "downstream_ui_id": "b"},
        {"upstream_ui_id": "b", "downstream_ui_id": "c"},
    ]
    payload = {"nodes": nodes, "edges": edges}
    body = client.post(
        "/api/jobs/pipeline/submit", json=payload, headers=headers
    ).json()

    cancel = f"/api/runs/{body['run_id']}/cancel"
    counts = client.post(cancel, headers=headers).json()
    assert (counts["cancelled"], counts["cancelling"]) == (3, 0)
