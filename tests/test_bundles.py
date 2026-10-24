"""
Run zips ("bundles"): a run closes exactly once, even when its last
two jobs finish together; house runs are zipped automatically; runs
whose files stay on the user's machine show where they are and are
zipped only on request; old zips expire.
"""

import asyncio
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.main import create_store
from app.models.compute_target import HOUSE_TARGET_ID, ComputeTarget
from app.models.job import Job
from app.models.run import Run
from app.runs.bundles import PACK_TIMEOUT
from app.runs.lifecycle import complete_attempt
from app.runs.states import JobStatus
from app.storage.keys import bundle_key
from tests.graphs import build_graph, commit_changes
from tests.test_agent_api import (
    HOUSE,
    claim,
    complete,
    drain_queue,
    submit_chain,
)
from tests.test_sweeper import with_sweeper

UserHeadersFactory = Callable[..., dict[str, str]]
FOLDER = {
    "path": "/scratch/you/atomfield/runs/r",
    "address": "you@login.hpc.edu",
}


@pytest.fixture
def chain(client: TestClient, make_user_headers: UserHeadersFactory):
    """
    A fresh two-job chain (first -> second) on the house queue.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :return: (owner headers, [first id, second id]).
    :rtype: tuple[dict[str, str], list[str]]
    """
    drain_queue()
    headers = make_user_headers()
    return headers, submit_chain(client, headers)


def run_of(client: TestClient, headers: dict, job_id: str) -> str:
    """
    The run a job belongs to.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Owner headers.
    :type headers: dict
    :param job_id: Any job of the run.
    :type job_id: str
    :return: Run id.
    :rtype: str
    """
    return client.get(f"/api/jobs/{job_id}", headers=headers).json()["run_id"]


def finish_chain(client: TestClient, chain, **report) -> dict:
    """
    Run both jobs of the chain to success through the agent API.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    :param report: Extra completion fields (e.g. ``folder``).
    :type report: Any
    :return: The reply to the report that finished the run.
    :rtype: dict
    """
    _, (first, second) = chain
    complete(client, first, claim(client).json()["attempt"], **report)
    reply = complete(client, second, claim(client).json()["attempt"], **report)
    return reply.json()


def bundle_report(client: TestClient, run_id: str, **body):
    """
    Report how packing a run ended, as the house agent.

    :param client: In-process API client.
    :type client: TestClient
    :param run_id: The run.
    :type run_id: str
    :param body: Report fields.
    :type body: Any
    :return: HTTP response.
    :rtype: httpx.Response
    """
    url = f"/api/agent/runs/{run_id}/bundle"
    return client.post(url, json=body, headers=HOUSE)


@pytest.fixture
def results_stay(make_session: async_sessionmaker) -> Iterator[None]:
    """
    Make the house target behave like a cluster or a laptop: results
    stay where they ran and are zipped only on request.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :return: Nothing; restores automatic zips afterwards.
    :rtype: Iterator[None]
    """

    async def set_automatic(value: bool) -> None:
        async with make_session() as session:
            await session.execute(
                update(ComputeTarget)
                .where(ComputeTarget.id == HOUSE_TARGET_ID)
                .values(bundles_automatically=value)
            )
            await session.commit()

    asyncio.run(set_automatic(False))
    try:
        yield
    finally:
        asyncio.run(set_automatic(True))


def test_a_finished_house_run_is_zipped_and_downloadable(
    client: TestClient,
    chain,
):
    """
    The reply that finishes a house run asks for its zip; once
    uploaded and reported, the owner gets a working download link and
    no folder (ours, not theirs). A second report is refused.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    """
    headers, _ = chain
    (pack,) = finish_chain(client, chain)["pack"]
    nodes = [job["node"] for job in pack["manifest"]["jobs"]]
    assert nodes == ["first", "second"]
    assert client.put(pack["upload_url"], content=b"PK zip").status_code == 201
    ready = {"status": "ready", "size_bytes": 6}
    assert bundle_report(client, pack["run_id"], **ready).status_code == 204

    url = f"/api/runs/{pack['run_id']}/bundle"
    info = client.get(url, headers=headers).json()
    assert (info["status"], info["size_bytes"]) == ("ready", 6)
    assert info["folder"] is None
    download = client.get(info["download_url"])
    assert download.content == b"PK zip"
    assert pack["bundle_name"] in download.headers["content-disposition"]
    assert bundle_report(client, pack["run_id"], **ready).status_code == 409


def test_results_that_stay_show_where_they_are(
    client: TestClient,
    chain,
    results_stay: None,
):
    """
    A run on a target that keeps its files is not zipped when it
    finishes; the owner sees its folder and an rsync command, and a
    zip is made only on request (handed out with the next heartbeat).

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    :param results_stay: Turns automatic zips off.
    :type results_stay: None
    """
    headers, (first, _) = chain
    assert finish_chain(client, chain, folder=FOLDER)["pack"] == []
    url = f"/api/runs/{run_of(client, headers, first)}/bundle"

    info = client.get(url, headers=headers).json()
    assert (info["finished"], info["status"]) == (True, "none")
    assert info["folder"]["copy_command"].startswith(
        "rsync -avz you@login.hpc.edu:/scratch/you/atomfield/runs/r/ ./"
    )

    assert client.post(url, headers=headers).json()["status"] == "requested"
    beat = client.post("/api/agent/heartbeat", json={"jobs": []}, headers=HOUSE)
    (pack,) = beat.json()["pack"]
    too_big = {"status": "too_big", "size_bytes": 2_000_000_000}
    assert bundle_report(client, pack["run_id"], **too_big).status_code == 204
    assert client.get(url, headers=headers).json()["status"] == "too_big"


def test_a_running_run_cannot_be_zipped_yet(client: TestClient, chain):
    """
    Asking for the zip of an unfinished run is a conflict.

    :param client: In-process API client.
    :type client: TestClient
    :param chain: Owner headers and job ids.
    :type chain: tuple
    """
    headers, (first, _) = chain
    url = f"/api/runs/{run_of(client, headers, first)}/bundle"
    assert client.post(url, headers=headers).status_code == 409
    assert client.get(url, headers=headers).json()["finished"] is False


def test_the_last_two_jobs_finishing_together_close_the_run(
    make_session: async_sessionmaker,
):
    """
    Two leaves of one run finish in two transactions at once. Each
    alone sees the other still running; the check made while the run's
    row is locked lets the second see the first's change, so the run
    closes (and, on the house target, its zip is requested).

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """

    async def finish(job_id: uuid.UUID) -> None:
        async with make_session() as session:
            await complete_attempt(session, job_id, JobStatus.SUCCEEDED)
            await asyncio.sleep(0.05)  # both changes are in flight
            await commit_changes(session)

    async def scenario():
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B"), ("C", "D")])
            for name, status in (("A", "succeeded"), ("C", "succeeded")):
                await session.execute(
                    update(Job).where(Job.id == ids[name]).values(status=status)
                )
            for name in ("B", "D"):
                await session.execute(
                    update(Job)
                    .where(Job.id == ids[name])
                    .values(status="running", pending_parents=0)
                )
            await session.commit()
            run_id = (await session.get(Job, ids["B"])).run_id
        await asyncio.gather(finish(ids["B"]), finish(ids["D"]))
        async with make_session() as session:
            run = await session.get(Run, run_id)
            return run.finished_at is not None, run.bundle_status

    assert asyncio.run(scenario()) == (True, "requested")


def test_the_sweeper_expires_zips_and_retries_silent_packing(
    make_session: async_sessionmaker,
):
    """
    A ready zip past its keep time is deleted and marked expired; a
    zip "packing" for too long is requested again.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    store = create_store()

    async def scenario(sweeper, redis):
        async with make_session() as session:
            ids = await build_graph(session, [("A", "B")])
            old_id = (await session.get(Job, ids["A"])).run_id
            ids = await build_graph(session, [("C", "D")])
            stuck_id = (await session.get(Job, ids["C"])).run_id
            await session.execute(
                update(Run)
                .where(Run.id == old_id)
                .values(
                    bundle_status="ready",
                    bundle_expires_at=func.now() - PACK_TIMEOUT,
                )
            )
            await session.execute(
                update(Run)
                .where(Run.id == stuck_id)
                .values(
                    bundle_status="packing",
                    bundle_requested_at=func.now() - 2 * PACK_TIMEOUT,
                )
            )
            await session.commit()
        await store.write(bundle_key(old_id), b"old zip")
        report = await sweeper.sweep_once()
        async with make_session() as session:
            old = await session.get(Run, old_id)
            stuck = await session.get(Run, stuck_id)
        gone = await store.read(bundle_key(old_id)) is None
        return report, old.bundle_status, stuck.bundle_status, gone

    report, old, stuck, gone = with_sweeper(make_session, scenario)
    assert (report.expired, report.repacked) == (1, 1)
    assert (old, stuck, gone) == ("expired", "requested", True)
