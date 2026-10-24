"""
Signed links and the local store: a link allows exactly one action on
one file until it expires, and the store never leaves its folder.
"""

import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.storage.links import DOWNLOAD, UPLOAD, LinkGrant, LinkSigner
from app.storage.store import (
    InvalidKeyError,
    LocalDiskStore,
    validate_filename,
    validate_key,
)

SIGNER = LinkSigner("test-secret")
GRANT = LinkGrant(UPLOAD, "runs/r1/bundle.zip", 2_000_000_000, 1024)
KB = 1024


def store_of(client: TestClient) -> LocalDiskStore:
    """
    The store the running app uses.

    :param client: In-process API client.
    :type client: TestClient
    :return: The app's store.
    :rtype: LocalDiskStore
    """
    return client.app.state.store


def with_query(link: str, **changes: str) -> str:
    """
    Rewrite query fields of a link, as a tamperer would.

    :param link: Signed link.
    :type link: str
    :param changes: Fields to replace.
    :type changes: str
    :return: The edited link.
    :rtype: str
    """
    parts = urlsplit(link)
    query = {name: values[0] for name, values in parse_qs(parts.query).items()}
    return f"{parts.path}?{urlencode({**query, **changes})}"


@pytest.mark.parametrize(
    "tampered",
    [
        LinkGrant(DOWNLOAD, GRANT.key, GRANT.expires, GRANT.max_bytes),
        LinkGrant(UPLOAD, "runs/r2/bundle.zip", GRANT.expires, 1024),
        LinkGrant(UPLOAD, GRANT.key, GRANT.expires + 1, 1024),
        LinkGrant(UPLOAD, GRANT.key, GRANT.expires, 2048),
        LinkGrant(UPLOAD, GRANT.key, GRANT.expires, 1024, "other.zip"),
    ],
    ids=["method", "key", "expiry", "size", "filename"],
)
def test_a_signature_fits_only_its_own_grant(tampered: LinkGrant):
    """
    Changing any signed field invalidates the signature.

    :param tampered: The grant with one field changed.
    :type tampered: LinkGrant
    """
    signature = SIGNER.sign(GRANT)
    assert SIGNER.verify(GRANT, signature, time.time())
    assert not SIGNER.verify(tampered, signature, time.time())


def test_an_expired_link_is_refused():
    """
    A correctly signed link stops working after its expiry.
    """
    signature = SIGNER.sign(GRANT)
    assert not SIGNER.verify(GRANT, signature, GRANT.expires + 1)


def test_another_secret_cannot_sign_links():
    """
    A signature made with a different secret is worthless.
    """
    forged = LinkSigner("guessed-secret").sign(GRANT)
    assert not SIGNER.verify(GRANT, forged, time.time())


@pytest.mark.parametrize(
    "key",
    ["../etc/passwd", "/abs/path", "a//b", "a/./b", "a/../b", "a\\b", "a\nb"],
)
def test_unsafe_keys_are_rejected(key: str, tmp_path: Path):
    """
    No key can name a file outside the store's folder.

    :param key: An unsafe key.
    :type key: str
    :param tmp_path: Empty folder for the store.
    :type tmp_path: Path
    """
    with pytest.raises(InvalidKeyError):
        validate_key(key)
    with pytest.raises(InvalidKeyError):
        LocalDiskStore(tmp_path, SIGNER).path_for(key)


def test_a_symlink_cannot_lead_out_of_the_store(tmp_path: Path):
    """
    A key can be plain text and still escape through a symlink inside
    the store; the resolved path is checked against the root too.

    :param tmp_path: Empty folder for the store and an outside folder.
    :type tmp_path: Path
    """
    root, outside = tmp_path / "store", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "runs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(InvalidKeyError):
        LocalDiskStore(root, SIGNER).path_for("runs/secret.txt")


def test_a_download_name_must_be_one_plain_name():
    """
    A path is not a file name.
    """
    assert validate_filename("water run.zip") == "water run.zip"
    with pytest.raises(InvalidKeyError):
        validate_filename("dir/water.zip")


def test_an_upload_link_stores_and_a_download_link_serves(
    client: TestClient,
):
    """
    The round trip a run zip takes: upload through one link, download
    through another, saved under the name the link gives.

    :param client: In-process API client.
    :type client: TestClient
    """
    store = store_of(client)
    key = "tests/roundtrip/bundle.zip"
    put = client.put(store.upload_link(key, KB, 60), content=b"zip bytes")
    assert put.status_code == 201
    assert put.json() == {"key": key, "size_bytes": 9}

    get = client.get(store.download_link(key, 60, filename="water.zip"))
    assert get.status_code == 200
    assert get.content == b"zip bytes"
    assert 'filename="water.zip"' in get.headers["content-disposition"]


def test_links_are_refused_when_altered_reused_or_expired(
    client: TestClient,
):
    """
    Over HTTP: a changed signature, another file, a download link used
    to upload, and an expired link all get 403.

    :param client: In-process API client.
    :type client: TestClient
    """
    store = store_of(client)
    key = "tests/refused/file.txt"
    upload = store.upload_link(key, KB, 60)
    download = store.download_link(key, 60)
    assert client.put(upload, content=b"x").status_code == 201

    forged = with_query(download, signature="0" * 64)
    other_file = download.replace("file.txt", "other.txt")
    expired = store.download_link(key, -1)
    assert client.get(forged).status_code == 403
    assert client.get(other_file).status_code == 403
    assert client.put(download, content=b"y").status_code == 403
    assert client.get(expired).status_code == 403
    assert client.get(download).content == b"x"


def test_an_upload_past_its_limit_is_refused_and_not_stored(
    client: TestClient,
):
    """
    Too large by its declared length, or by what actually arrives (a
    streamed body has no length up front): 413, and no file appears.

    :param client: In-process API client.
    :type client: TestClient
    """
    store = store_of(client)
    key = "tests/limit/big.bin"
    link = store.upload_link(key, KB, 60)

    def streamed():
        for _ in range(4):
            yield b"z" * KB

    assert client.put(link, content=b"z" * (KB + 1)).status_code == 413
    assert client.put(link, content=streamed()).status_code == 413
    assert store.existing_path(key) is None
    assert list(store.path_for(key).parent.glob("*")) == []


def test_a_missing_file_is_not_found(client: TestClient):
    """
    A valid link to a file that is gone (expired and swept) gets 404.

    :param client: In-process API client.
    :type client: TestClient
    """
    link = store_of(client).download_link("tests/missing/none.zip", 60)
    assert client.get(link).status_code == 404
