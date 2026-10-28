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
import hashlib
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

import httpx

from app.core.config import settings
from app.releases.publish import DEFAULT_API_URL, PublishError

CHUNK_BYTES = 1024 * 1024
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


def sha256_of(path: Path) -> str:
    """
    The fingerprint of a file.

    :param path: The file.
    :type path: Path
    :return: Its sha256, in hex.
    :rtype: str
    """
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def already_published(
    api_url: str, name: str, version: str, sha256: str
) -> bool:
    """
    Whether the server already has this exact pack.

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
    :raises PublishError: If that version exists with other contents.
    """
    response = httpx.get(f"{api_url.rstrip('/')}/api/data-packs", timeout=30.0)
    response.raise_for_status()
    for pack in response.json():
        if (pack["name"], pack["version"]) == (name, version):
            if pack["sha256"] != sha256:
                raise PublishError(
                    f"{name} {version} is already published with other "
                    "contents; give the change a new version"
                )
            return True
    return False


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
    :raises PublishError: If the server refused it.
    """
    headers = {
        "X-API-Key": admin_key,
        "Content-Length": str(archive.stat().st_size),
    }
    response = httpx.post(
        f"{api_url.rstrip('/')}/api/data-packs",
        params=query,
        content=file_chunks(archive),
        headers=headers,
        timeout=UPLOAD_SECONDS,
    )
    if response.status_code not in (200, 201):
        raise PublishError(f"The API refused it: {response.text}")
    return response.json()


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
    with tempfile.TemporaryDirectory() as scratch:
        archive = prepare_zip(source, Path(scratch))
        sha256 = sha256_of(archive)
        if already_published(api_url, name, version, sha256):
            return f"{name} {version} is already published; nothing sent."
        query = {"name": name, "version": version, "sha256": sha256}
        pack = upload_pack(api_url, admin_key, archive, query)
    size = pack["size_bytes"] / MEGABYTE
    return f"Published {name} {version} ({size:.0f} MB, sha256 {sha256[:12]})."


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


def main(argv: list[str] | None = None) -> int:
    """
    Command line: publish, and print what happened.

    :param argv: Arguments; None reads them from the command line.
    :type argv: list[str] | None
    :return: Exit code.
    :rtype: int
    """
    options = build_parser().parse_args(argv)
    admin_key = settings.ADMIN_API_KEY
    if not admin_key:
        print("Error: set ADMIN_API_KEY", file=sys.stderr)
        return 1
    try:
        print(
            publish_pack(
                options.source,
                options.name,
                options.version,
                options.api_url,
                admin_key,
            )
        )
    except (PublishError, httpx.HTTPError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
