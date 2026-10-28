"""
Data packs on the server: a zip is kept only if it is the one the
publisher announced, a version never changes, a release cannot name a
pack that does not exist, and a job's order carries its packs.
"""

import asyncio
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.data_pack import DataPack
from app.releases import data_packs
from app.releases.wheel import InvalidReleaseError, read_release
from tests.fake_release import FIXTURE_CATALOG, make_release
from tests.test_agent_api import claim, submit_chain
from tests.test_agent_archives import zipped

NEED = {"name": "toy-data", "version": "1", "env": "TOY_DATA"}


def upload(
    client: TestClient,
    headers: dict[str, str],
    data: bytes,
    sha256: str | None = None,
):
    """
    Publish ``data`` as ``toy-data 1``.

    :param client: In-process API client.
    :type client: TestClient
    :param headers: Caller's key headers.
    :type headers: dict[str, str]
    :param data: The zip.
    :type data: bytes
    :param sha256: Announced fingerprint; the real one by default.
    :type sha256: str | None
    :return: HTTP response.
    :rtype: httpx.Response
    """
    params = {
        "name": NEED["name"],
        "version": NEED["version"],
        "sha256": sha256 or hashlib.sha256(data).hexdigest(),
    }
    return client.post(
        "/api/data-packs", content=data, params=params, headers=headers
    )


def catalog_needing(need: dict) -> str:
    """
    The fixture catalog, with ``toy_opt`` reading a data pack.

    :param need: The data pack it reads.
    :type need: dict
    :return: Catalog JSON.
    :rtype: str
    """
    document = json.loads(FIXTURE_CATALOG.read_text())
    document["tasks"][0]["data"] = [need]
    return json.dumps(document)


def test_a_pack_is_kept_only_if_it_is_the_announced_zip(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers,
    releases,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Only the administrator publishes; a wrong fingerprint, a file that
    is not a zip, or a file past the size limit is not kept; the same
    pack again changes nothing; other contents under the same version
    are refused.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Administrator headers.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param releases: Cleans up publications afterwards.
    :type releases: None
    :param monkeypatch: Lowers the size limit.
    :type monkeypatch: pytest.MonkeyPatch
    """
    data = zipped({"table.txt": "Fe Fe.UPF\n"})
    assert upload(client, make_user_headers(), data).status_code == 403
    wrong = upload(client, admin_headers, data, sha256="0" * 64)
    assert wrong.status_code == 422
    assert upload(client, admin_headers, b"plain text").status_code == 422
    with monkeypatch.context() as patch:
        patch.setattr(data_packs, "MAX_DATA_PACK_BYTES", 10)
        assert upload(client, admin_headers, data).status_code == 413
    assert client.get("/api/data-packs").json() == []

    first = upload(client, admin_headers, data)
    assert (first.status_code, first.json()["size_bytes"]) == (201, len(data))
    assert upload(client, admin_headers, data).status_code == 200
    changed = zipped({"table.txt": "changed\n"})
    assert upload(client, admin_headers, changed).status_code == 409
    listed = client.get("/api/data-packs").json()
    assert [(pack["name"], pack["version"]) for pack in listed] == [
        ("toy-data", "1")
    ]


def test_a_release_needs_its_packs_and_a_claim_carries_them(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers,
    releases,
):
    """
    A release naming a pack that does not exist is refused; once the
    pack is published it is accepted; the job's order names the pack,
    its variable and a link to exactly its bytes; the run's files say
    what made them.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Administrator headers.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param releases: Cleans up publications afterwards.
    :type releases: None
    """
    wheel = make_release("3.0.0", {"toy/catalog.json": catalog_needing(NEED)})
    refused = client.post("/api/releases", content=wheel, headers=admin_headers)
    assert refused.status_code == 422
    assert "toy-data 1" in refused.json()["detail"]

    data = zipped({"table.txt": "Fe Fe.UPF\n"})
    upload(client, admin_headers, data)
    accepted = client.post(
        "/api/releases", content=wheel, headers=admin_headers
    )
    assert accepted.status_code == 201
    headers = make_user_headers()
    submit_chain(client, headers)
    order = claim(client).json()
    [pack] = order["data"]
    assert (pack["name"], pack["version"], pack["env"]) == (
        "toy-data",
        "1",
        "TOY_DATA",
    )
    assert client.get(pack["url"]).content == data
    files = client.get(f"/api/runs/{order['run_id']}/bundle", headers=headers)
    assert files.json()["made_with"] == "toy 3.0.0"
    assert files.json()["data_packs"] == ["toy-data 1"]


def test_a_job_whose_pack_is_gone_fails_before_it_starts(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers,
    make_session: async_sessionmaker,
    releases,
):
    """
    If a needed pack is missing when a job is claimed, the job fails
    with a message naming it instead of starting without its data.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Administrator headers.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param releases: Cleans up publications afterwards.
    :type releases: None
    """
    upload(client, admin_headers, zipped({"table.txt": ""}))
    wheel = make_release("3.0.0", {"toy/catalog.json": catalog_needing(NEED)})
    client.post("/api/releases", content=wheel, headers=admin_headers)
    headers = make_user_headers()
    first, _ = submit_chain(client, headers)

    async def lose_the_pack():
        async with make_session() as session:
            await session.execute(delete(DataPack))
            await session.commit()

    asyncio.run(lose_the_pack())
    assert claim(client).status_code == 204
    job = client.get(f"/api/jobs/{first}", headers=headers).json()
    assert job["status"] == "failed"
    assert "toy-data 1" in job["error_message"]


def test_a_task_cannot_take_a_variable_the_agent_sets():
    """
    A data pack may not replace ``PYTHONPATH`` or another variable the
    agent sets for every job.
    """
    need = {**NEED, "env": "PYTHONPATH"}
    catalog = {"toy/catalog.json": catalog_needing(need)}
    with pytest.raises(InvalidReleaseError, match="PYTHONPATH is set by"):
        read_release(make_release(replace=catalog))
