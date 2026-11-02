"""
Where each kind of file lives in the store: one place, so every reader
and writer agrees on the layout.

    uploads/<user>/<session>/<file>    what a user uploaded
    runs/<run>/jobs/<job>/<file>       files the UI shows for one job
    runs/<run>/bundle.zip              everything of a run, zipped
    releases/<sha256>.whl              a scripts release, by fingerprint
    data/<name>/<version>.zip          a data pack
"""

import uuid

from app.core.identifiers import sanitize_identifier, user_folder_name
from app.storage.store import validate_filename

UPLOADS = "uploads"
RUNS = "runs"
ANONYMOUS = "anonymous"
BUNDLE_NAME = "bundle.zip"
RELEASES = "releases"
DATA = "data"


def owner_folder(owner_id: uuid.UUID | None) -> str:
    """
    The folder of a run's owner.

    :param owner_id: Owner's API key id, if any.
    :type owner_id: uuid.UUID | None
    :return: User folder name.
    :rtype: str
    """
    return user_folder_name(owner_id) if owner_id else ANONYMOUS


def upload_folder(owner_id: uuid.UUID | None, session_id: str) -> str:
    """
    Folder of the files uploaded into one session.

    :param owner_id: Uploader's API key id.
    :type owner_id: uuid.UUID | None
    :param session_id: UI session (pipeline id).
    :type session_id: str
    :return: ``uploads/<user>/<session>``.
    :rtype: str
    """
    session = sanitize_identifier(session_id)
    return f"{UPLOADS}/{owner_folder(owner_id)}/{session}"


def upload_key(owner_id: uuid.UUID | None, session_id: str, name: str) -> str:
    """
    Key of a file uploaded into a session.

    :param owner_id: Uploader's API key id.
    :type owner_id: uuid.UUID | None
    :param session_id: UI session (pipeline id).
    :type session_id: str
    :param name: File name.
    :type name: str
    :return: ``uploads/<user>/<session>/<name>``.
    :rtype: str
    :raises InvalidKeyError: If the name is not a plain file name.
    """
    folder = upload_folder(owner_id, session_id)
    return f"{folder}/{validate_filename(name)}"


def job_file_key(run_id: uuid.UUID, job_id: uuid.UUID, name: str) -> str:
    """
    Key of a file the UI shows for one job (its log, small outputs).

    :param run_id: The job's run.
    :type run_id: uuid.UUID
    :param job_id: The job.
    :type job_id: uuid.UUID
    :param name: File name.
    :type name: str
    :return: ``runs/<run>/jobs/<job>/<name>``.
    :rtype: str
    """
    return f"{RUNS}/{run_id}/jobs/{job_id}/{validate_filename(name)}"


def ai_sent_key(run_id: uuid.UUID, review_id: uuid.UUID) -> str:
    """
    Key of the exact text sent to a model for one review. It sits beside
    the run's jobs, so the job file routes can't reach it, and it goes
    when the run is deleted.

    :param run_id: The job's run.
    :type run_id: uuid.UUID
    :param review_id: The review.
    :type review_id: uuid.UUID
    :return: ``runs/<run>/ai/<review>.txt``.
    :rtype: str
    """
    return f"{RUNS}/{run_id}/ai/{review_id}.txt"


def run_files_folder(run_id: uuid.UUID) -> str:
    """
    Folder of everything stored for one run (UI files and its zip).

    :param run_id: The run.
    :type run_id: uuid.UUID
    :return: ``runs/<run>``.
    :rtype: str
    """
    return f"{RUNS}/{run_id}"


def owner_uploads_folder(owner_id: uuid.UUID | None) -> str:
    """
    Folder of everything one user uploaded, across sessions.

    :param owner_id: The user's API key id.
    :type owner_id: uuid.UUID | None
    :return: ``uploads/<user>``.
    :rtype: str
    """
    return f"{UPLOADS}/{owner_folder(owner_id)}"


def bundle_key(run_id: uuid.UUID) -> str:
    """
    Key of a run's zip.

    :param run_id: The run.
    :type run_id: uuid.UUID
    :return: ``runs/<run>/bundle.zip``.
    :rtype: str
    """
    return f"{RUNS}/{run_id}/{BUNDLE_NAME}"


def release_key(sha256: str) -> str:
    """
    Key of a release's wheel. Named by its fingerprint, so the same
    file is always stored at the same place and never overwritten by
    different content.

    :param sha256: The wheel's fingerprint (hex).
    :type sha256: str
    :return: ``releases/<sha256>.whl``.
    :rtype: str
    """
    return f"{RELEASES}/{sha256}.whl"


def data_pack_key(name: str, version: str) -> str:
    """
    Key of a data pack's zip. A name and version are published once,
    so the key never holds two different files.

    :param name: The pack's name.
    :type name: str
    :param version: Its version.
    :type version: str
    :return: ``data/<name>/<version>.zip``.
    :rtype: str
    :raises InvalidKeyError: If the name or version is a path.
    """
    folder = validate_filename(name)
    return f"{DATA}/{folder}/{validate_filename(f'{version}.zip')}"
