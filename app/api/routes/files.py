"""
app/api/routes/files.py — Molecular Structure Asset Upload & Parsing API.
"""

import uuid
from collections import Counter
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel

from app.api.dependencies import get_optional_api_key
from app.core.config import settings
from app.models.api_key import ApiKey
from app.services.job_service import sanitize_identifier

router = APIRouter(prefix="/files", tags=["Files"])

ARTIFACTS_DIR = Path(settings.ARTIFACTS_DIR)
MAX_FILE_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".xyz", ".mol", ".sdf", ".pdb"}


class AtomCoordinate(BaseModel):
    """
    Three-dimensional atomic coordinate model.
    """

    index: int
    element: str
    x: float
    y: float
    z: float


class StructureMetadata(BaseModel):
    """
    Extracted chemical and geometric metadata for molecular asset.
    """

    file_id: str
    filename: str
    workspace_path: str
    session_id: str
    size_bytes: int
    atom_count: int
    formula: str
    comment: str
    elements: dict[str, int]
    atoms: list[AtomCoordinate]
    bounding_box: dict[str, float] | None = None
    raw_content: str


def _format_carbon_hill_formula(counts: Counter) -> list[str]:
    """
    Format element symbols for systems containing carbon (C first, then H).

    :param counts: Counter mapping element symbols to atom frequencies.
    :type counts: Counter
    :return: List of formatted symbol strings.
    :rtype: list[str]
    """
    formula_parts = []
    carbon_count = counts["C"]
    formula_parts.append(f"C{carbon_count if carbon_count > 1 else ''}")
    if "H" in counts:
        hydrogen_count = counts["H"]
        formula_parts.append(f"H{hydrogen_count if hydrogen_count > 1 else ''}")
    for element_symbol in sorted(counts.keys()):
        if element_symbol not in ("C", "H"):
            frequency = counts[element_symbol]
            formula_parts.append(
                f"{element_symbol}{frequency if frequency > 1 else ''}"
            )
    return formula_parts


def _format_non_carbon_hill_formula(counts: Counter) -> list[str]:
    """
    Format element symbols alphabetically for systems without carbon.

    :param counts: Counter mapping element symbols to atom frequencies.
    :type counts: Counter
    :return: List of formatted symbol strings.
    :rtype: list[str]
    """
    formula_parts = []
    for element_symbol in sorted(counts.keys()):
        frequency = counts[element_symbol]
        formula_parts.append(
            f"{element_symbol}{frequency if frequency > 1 else ''}"
        )
    return formula_parts


def format_hill_formula(counts: Counter) -> str:
    """
    Format chemical formula using standard Hill system notation.

    :param counts: Element frequency counter.
    :type counts: Counter
    :return: Assembled Hill formula string.
    :rtype: str
    """
    if not counts:
        return "Unknown"
    if "C" in counts:
        parts = _format_carbon_hill_formula(counts)
    else:
        parts = _format_non_carbon_hill_formula(counts)
    return "".join(parts) or "Unknown"


def _parse_coordinate_tokens(
    line_index: int,
    line_tokens: list[str],
) -> tuple[AtomCoordinate | None, float, float, float]:
    """
    Parse a single XYZ atom line into an AtomCoordinate instance.

    :param line_index: One-based index of the coordinate line.
    :type line_index: int
    :param line_tokens: Whitespace-split line tokens.
    :type line_tokens: list[str]
    :return: Tuple of coordinate entity and float position components.
    :rtype: tuple
    """
    element_symbol = line_tokens[0].capitalize()
    coord_x, coord_y, coord_z = (
        float(line_tokens[1]),
        float(line_tokens[2]),
        float(line_tokens[3]),
    )
    atom_entity = AtomCoordinate(
        index=line_index,
        element=element_symbol,
        x=coord_x,
        y=coord_y,
        z=coord_z,
    )
    return atom_entity, coord_x, coord_y, coord_z


def _record_atom_coordinate(
    atoms: list[AtomCoordinate],
    counts: Counter,
    coords: tuple[list[float], list[float], list[float]],
    atom_entity: AtomCoordinate,
    pos: tuple[float, float, float],
) -> None:
    """
    Append parsed atom entity and record element counts and coordinates.

    :param atoms: Accumulator list of atoms.
    :type atoms: list[AtomCoordinate]
    :param counts: Accumulator counter of element frequencies.
    :type counts: Counter
    :param coords: Tuple of (x_coords, y_coords, z_coords) lists.
    :type coords: tuple
    :param atom_entity: Parsed AtomCoordinate instance.
    :type atom_entity: AtomCoordinate
    :param pos: Tuple of (x, y, z) position floats.
    :type pos: tuple[float, float, float]
    """
    atoms.append(atom_entity)
    counts[atom_entity.element] += 1
    coords[0].append(pos[0])
    coords[1].append(pos[1])
    coords[2].append(pos[2])


def _process_coord_line(
    line_index: int,
    line_content: str,
    atoms: list[AtomCoordinate],
    counts: Counter,
    coords: tuple[list[float], list[float], list[float]],
) -> None:
    """
    Parse a single coordinate line and append to atom accumulators.

    :param line_index: One-based line number.
    :type line_index: int
    :param line_content: Line string content.
    :type line_content: str
    :param atoms: Accumulator list of atoms.
    :type atoms: list[AtomCoordinate]
    :param counts: Accumulator counter of element frequencies.
    :type counts: Counter
    :param coords: Tuple of position coordinate lists.
    :type coords: tuple
    """
    line_tokens = line_content.split()
    if len(line_tokens) >= 4:
        try:
            entity, pos_x, pos_y, pos_z = _parse_coordinate_tokens(
                line_index, line_tokens
            )
            _record_atom_coordinate(
                atoms, counts, coords, entity, (pos_x, pos_y, pos_z)
            )
        except ValueError:
            pass


def _parse_atom_coordinates(coord_lines: list[str]):
    """
    Parse coordinate lines and collect spatial coordinates.

    :param coord_lines: Raw coordinate text lines.
    :type coord_lines: list[str]
    :return: Tuple of (atoms, element_counts, (x_coords, y_coords, z_coords)).
    :rtype: tuple
    """
    atoms: list[AtomCoordinate] = []
    counts: Counter = Counter()
    coords: tuple[list[float], list[float], list[float]] = ([], [], [])
    for line_index, line_content in enumerate(coord_lines, start=1):
        _process_coord_line(line_index, line_content, atoms, counts, coords)
    return atoms, counts, coords


def _calculate_bounding_box(
    x_coords: list[float],
    y_coords: list[float],
    z_coords: list[float],
) -> dict[str, float] | None:
    """
    Calculate bounding box dimensions for molecular geometry.

    :param x_coords: List of X positions.
    :type x_coords: list[float]
    :param y_coords: List of Y positions.
    :type y_coords: list[float]
    :param z_coords: List of Z positions.
    :type z_coords: list[float]
    :return: Bounding box dictionary if coordinates present, else None.
    :rtype: dict[str, float] | None
    """
    if not (x_coords and y_coords and z_coords):
        return None
    return {
        "min_x": round(min(x_coords), 3),
        "max_x": round(max(x_coords), 3),
        "span_x": round(max(x_coords) - min(x_coords), 3),
        "min_y": round(min(y_coords), 3),
        "max_y": round(max(y_coords), 3),
        "span_y": round(max(y_coords) - min(y_coords), 3),
        "min_z": round(min(z_coords), 3),
        "max_z": round(max(z_coords), 3),
        "span_z": round(max(z_coords) - min(z_coords), 3),
    }


def parse_xyz_content(content_str: str):
    """
    Parse standard XYZ coordinate content into atoms, formula, and bounds.

    :param content_str: Full string content of XYZ file.
    :type content_str: str
    :return: Tuple of (expected_count, comment, atoms, counts, bounding_box).
    :rtype: tuple
    """
    lines = [line.strip() for line in content_str.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Empty file")
    try:
        expected_atom_count = int(lines[0])
    except ValueError:
        expected_atom_count = len(lines) - 1
    comment = lines[1] if len(lines) > 1 else ""
    atoms, counts, coords = _parse_atom_coordinates(lines[2:])
    bounding_box = _calculate_bounding_box(*coords)
    return expected_atom_count, comment, atoms, counts, bounding_box


def _validate_uploaded_file(file: UploadFile) -> str:
    """
    Validate presence of filename and check against permitted extensions.

    :param file: Submitted multipart UploadFile object.
    :type file: UploadFile
    :return: Lowercase extension string.
    :rtype: str
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    clean_name = Path(file.filename).name
    extension = Path(clean_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
        detail_msg = (
            f"Unsupported file format '{extension}'. Allowed: {allowed_list}"
        )
        raise HTTPException(status_code=400, detail=detail_msg)
    return extension


async def _read_file_payload(file: UploadFile) -> tuple[bytes, str]:
    """
    Read uploaded file bytes and decode text content with safety limit.

    :param file: Submitted multipart UploadFile object.
    :type file: UploadFile
    :return: Tuple of raw bytes and decoded UTF-8 string.
    :rtype: tuple[bytes, str]
    """
    content_bytes = await file.read()
    if len(content_bytes) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400, detail="File too large (limit: 50MB)"
        )
    try:
        content_str = content_bytes.decode("utf-8", errors="replace")
        return content_bytes, content_str
    except (UnicodeDecodeError, ValueError) as error:
        detail_msg = f"Failed to decode file text: {error!s}"
        raise HTTPException(status_code=400, detail=detail_msg)


def _resolve_and_write_file(
    session_id: str,
    filename: str,
    content_str: str,
    user_id: str | None = None,
) -> Path:
    """
    Ensure session directory exists and write content preventing path traversal.

    :param session_id: Session identifier string.
    :type session_id: str
    :param filename: Base filename string.
    :type filename: str
    :param content_str: File text content to write.
    :type content_str: str
    :param user_id: Optional user identifier for directory isolation.
    :type user_id: str | None
    :return: Resolved written file Path.
    :rtype: Path
    """
    clean_session_id = sanitize_identifier(session_id)
    if user_id:
        clean_user_id = sanitize_identifier(user_id)
        dest_dir = (ARTIFACTS_DIR / clean_user_id / clean_session_id).resolve()
    else:
        dest_dir = (ARTIFACTS_DIR / clean_session_id).resolve()

    if not str(dest_dir).startswith(str(ARTIFACTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = (dest_dir / filename).resolve()
    if not str(dest_file).startswith(str(dest_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    dest_file.write_text(content_str, encoding="utf-8")
    return dest_file


def _extract_structure_metadata(extension: str, content_str: str):
    """
    Extract structure geometry and formula from content string.

    :param extension: Lowercase file extension (.xyz, .mol, etc.).
    :type extension: str
    :param content_str: File string content.
    :type content_str: str
    :return: Tuple of (atom_count, comment, atoms, counts, bounding_box).
    :rtype: tuple
    """
    if extension == ".xyz":
        try:
            exp_cnt, comment, atoms, counts, bbox = parse_xyz_content(
                content_str
            )
            atom_count = len(atoms) or exp_cnt
            return atom_count, comment, atoms, counts, bbox
        except (ValueError, IndexError) as parse_error:
            comment = f"Raw XYZ (unparsed: {parse_error!s})"
            return 0, comment, [], Counter(), None
    return 0, f"Structure file ({extension})", [], Counter(), None


def _build_structure_metadata(
    filename: str,
    session_id: str,
    content_bytes: bytes,
    content_str: str,
    parsed_info: tuple,
) -> StructureMetadata:
    """
    Assemble StructureMetadata response model from extracted attributes.

    :param filename: Base filename string.
    :type filename: str
    :param session_id: Target session identifier.
    :type session_id: str
    :param content_bytes: Raw binary file bytes.
    :type content_bytes: bytes
    :param content_str: Decoded string content.
    :type content_str: str
    :param parsed_info: Extracted (atom_count, comment, atoms, counts, bbox).
    :type parsed_info: tuple
    :return: StructureMetadata response instance.
    :rtype: StructureMetadata
    """
    atom_count, comment, atoms, counts, bbox = parsed_info
    return StructureMetadata(
        file_id=f"file_{uuid.uuid4().hex[:8]}",
        filename=filename,
        workspace_path=f"/workspace/{filename}",
        session_id=session_id,
        size_bytes=len(content_bytes),
        atom_count=atom_count,
        formula=format_hill_formula(counts),
        comment=comment,
        elements=dict(counts),
        atoms=atoms,
        bounding_box=bbox,
        raw_content=content_str[:50000],
    )


@router.post(
    "/upload",
    response_model=StructureMetadata,
    status_code=status.HTTP_201_CREATED,
)
async def upload_structure(
    file: UploadFile = File(...),
    session_id: str = Form("default"),
    api_key: ApiKey | None = Depends(get_optional_api_key),
):
    """
    Upload and parse molecular structure file into workspace.

    :param file: Submitted molecular file.
    :type file: UploadFile
    :param session_id: Associated session identifier.
    :type session_id: str
    :param api_key: Optional authenticated user API key.
    :type api_key: ApiKey | None
    :return: Parsed structure metadata model.
    :rtype: StructureMetadata
    """
    clean_filename = Path(file.filename or "structure.xyz").name
    extension = _validate_uploaded_file(file)
    content_bytes, content_str = await _read_file_payload(file)
    user_id = f"user_{api_key.id.hex[:12]}" if api_key else None
    _resolve_and_write_file(
        session_id, clean_filename, content_str, user_id=user_id
    )
    parsed_info = _extract_structure_metadata(extension, content_str)
    return _build_structure_metadata(
        clean_filename, session_id, content_bytes, content_str, parsed_info
    )
