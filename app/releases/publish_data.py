"""
Publish a data pack::

    python -m app.releases.publish_data ~/pseudo/pslibrary-rel-pbe \\
        --name pslibrary-rel-pbe --version 1.0.0

Give it a folder or a zip. A folder is zipped the same way every time
(files in name order, fixed timestamps, hidden files left out), so the
same files always make the same zip with the same fingerprint. Before
uploading, the command asks the server whether that pack is already
there, so an unchanged pack is never sent twice.
"""

import argparse
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from functools import partial
from pathlib import Path

import httpx

from app.core.cli import stops_cleanly
from app.core.fingerprints import file_sha256
from app.core.names import version_label
from app.releases.publish import (
    DEFAULT_API_URL,
    PublishError,
    accepted,
    admin_headers,
    call_api,
    run_with_admin_key,
)
from app.releases.published import already_published

DATA_PACKS_PATH = "/api/data-packs"
CHUNK_BYTES = 1024 * 1024
LIST_SECONDS = 30.0
# A pack can be hundreds of megabytes on a slow line.
UPLOAD_SECONDS = 3600.0
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o644 << 16
MEGABYTE = 1024 * 1024


def packed_files(folder: Path) -> list[Path]:
    """
    The files a folder's pack holds: all of them, in name order, except
    hidden ones (``.DS_Store`` and the like).

    :param folder: The folder.
    :type folder: Path
    :return: The files.
    :rtype: list[Path]
    """
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and not any(
            part.startswith(".") for part in path.relative_to(folder).parts
        )
    )


def zip_folder(folder: Path, destination: Path) -> None:
    """
    Zip a folder the same way every time, never holding a whole file
    in memory.

    :param folder: The folder.
    :type folder: Path
    :param destination: The zip to write.
    :type destination: Path
    """
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in packed_files(folder):
            info = zipfile.ZipInfo(
                path.relative_to(folder).as_posix(), ZIP_TIME
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = FILE_MODE
            with path.open("rb") as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target, CHUNK_BYTES)


def check_zip(path: Path) -> None:
    """
    Refuse a file that is not a sound zip.

    :param path: The file.
    :type path: Path
    :raises PublishError: If it is not a zip, or is damaged.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            damaged = archive.testzip()
    except zipfile.BadZipFile as error:
        raise PublishError(f"{path} is not a zip file") from error
    if damaged is not None:
        raise PublishError(f"{path} is damaged: {damaged}")


def prepare_zip(source: Path, scratch: Path) -> Path:
    """
    The zip to upload: the given zip, or the given folder zipped.

    :param source: A folder or a zip file.
    :type source: Path
    :param scratch: Temporary folder for a new zip.
    :type scratch: Path
    :return: A checked zip file.
    :rtype: Path
    """
    if source.is_dir():
        archive = scratch / f"{source.name}.zip"
        zip_folder(source, archive)
    else:
        archive = source
    check_zip(archive)
    return archive


def server_has(api_url: str, name: str, version: str, sha256: str) -> bool:
    """
    Whether the server already has this exact pack, asked before
    sending what can be hundreds of megabytes.

    :param api_url: The API's address.
    :type api_url: str
    :param name: The pack's name.
    :type name: str
    :param version: Its version.
    :type version: str
    :param sha256: The zip's fingerprint.
    :type sha256: str
    :return: True if it has.
    :rtype: bool
    :raises PublishConflictError: If that version exists with other
        contents.
    :raises PublishError: If the API cannot be reached, or refuses.
    """
    response = call_api(
        httpx.get, api_url, DATA_PACKS_PATH, timeout=LIST_SECONDS
    )
    published = {
        (pack["name"], pack["version"]): pack["sha256"]
        for pack in accepted(response)
    }
    label = version_label(name, version)
    return already_published(published.get((name, version)), sha256, label)


def file_chunks(path: Path) -> Iterator[bytes]:
    """
    A file's bytes in pieces, for streaming an upload.

    :param path: The file.
    :type path: Path
    :return: Its bytes, piece by piece.
    :rtype: Iterator[bytes]
    """
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            yield chunk


def upload_pack(
    api_url: str, admin_key: str, archive: Path, query: dict[str, str]
) -> dict:
    """
    Stream the zip to the server.

    :param api_url: The API's address.
    :type api_url: str
    :param admin_key: The administrator's key.
    :type admin_key: str
    :param archive: The zip.
    :type archive: Path
    :param query: Name, version and fingerprint.
    :type query: dict[str, str]
    :return: The published pack.
    :rtype: dict
    :raises PublishError: If the server refused it or was not there.
    """
    size = {"Content-Length": str(archive.stat().st_size)}
    response = call_api(
        httpx.post,
        api_url,
        DATA_PACKS_PATH,
        params=query,
        content=file_chunks(archive),
        headers={**admin_headers(admin_key), **size},
        timeout=UPLOAD_SECONDS,
    )
    return accepted(response)


def publish_pack(
    source: Path, name: str, version: str, api_url: str, admin_key: str
) -> str:
    """
    Zip (if needed), check and publish a data pack.

    :param source: A folder or a zip file.
    :type source: Path
    :param name: The pack's name.
    :type name: str
    :param version: Its version.
    :type version: str
    :param api_url: The API's address.
    :type api_url: str
    :param admin_key: The administrator's key.
    :type admin_key: str
    :return: What happened.
    :rtype: str
    """
    label = version_label(name, version)
    with tempfile.TemporaryDirectory() as scratch:
        archive = prepare_zip(source, Path(scratch))
        sha256 = file_sha256(archive)
        if server_has(api_url, name, version, sha256):
            return f"{label} is already published; nothing sent."
        query = {"name": name, "version": version, "sha256": sha256}
        pack = upload_pack(api_url, admin_key, archive, query)
    size = pack["size_bytes"] / MEGABYTE
    return f"Published {label} ({size:.0f} MB, sha256 {sha256[:12]})."


def build_parser() -> argparse.ArgumentParser:
    """
    Describe the command line.

    :return: Parser for ``python -m app.releases.publish_data``.
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.releases.publish_data",
        description="Publish a folder or zip of data as a data pack.",
    )
    parser.add_argument("source", type=Path, help="Folder or zip file")
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    return parser


@stops_cleanly(
    "Stopped. Publishing again is safe: unchanged files are not sent twice."
)
def main(argv: list[str] | None = None) -> int:
    """
    Command line: publish, and print what happened.

    :param argv: Arguments; None reads them from the command line.
    :type argv: list[str] | None
    :return: Exit code.
    :rtype: int
    """
    options = build_parser().parse_args(argv)
    publishing = partial(
        publish_pack,
        options.source,
        options.name,
        options.version,
        options.api_url,
    )
    return run_with_admin_key(publishing)


if __name__ == "__main__":
    raise SystemExit(main())
