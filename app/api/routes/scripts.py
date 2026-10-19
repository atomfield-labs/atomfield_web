"""
HTTP route handlers for simulation scripts and manifests.
"""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/scripts", tags=["Scripts"])


def get_manifest_path() -> Path:
    """
    Locate scripts manifest.json from local workspace or container mounts.

    :return: Resolved Path to manifest file.
    :rtype: Path
    """
    candidate_paths = [
        Path.cwd() / "scripts_repo" / "manifest.json",
        Path(__file__).resolve().parents[3] / "scripts_repo" / "manifest.json",
        Path("/app/scripts_repo/manifest.json"),
    ]
    for candidate_path in candidate_paths:
        if candidate_path.exists() and candidate_path.is_file():
            return candidate_path
    return candidate_paths[0]


def _read_manifest_from_disk(manifest_path: Path) -> list:
    """
    Synchronously read and parse manifest.json from filesystem.

    :param manifest_path: Path to target manifest file.
    :type manifest_path: Path
    :return: Parsed list of script metadata mappings.
    :rtype: list
    :raises HTTPException: If manifest cannot be parsed or read.
    """
    if not manifest_path.exists():
        return []
    try:
        with open(manifest_path, "r", encoding="utf-8") as manifest_file:
            return json.load(manifest_file)
    except (OSError, json.JSONDecodeError) as parse_error:
        error_detail = f"Failed to read scripts manifest: {parse_error!s}"
        raise HTTPException(
            status_code=500, detail=error_detail
        ) from parse_error


@router.get("/available")
async def get_available_scripts() -> list:
    """
    Return parsed manifest.json from the external scripts repository.

    :return: List of discovered script metadata items.
    :rtype: list
    """
    manifest_path = get_manifest_path()
    return await asyncio.to_thread(_read_manifest_from_disk, manifest_path)
