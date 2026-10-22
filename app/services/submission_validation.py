"""
Check submissions against the task catalog before anything is stored.

Errors use FastAPI's own 422 format, located at the exact request field
(``body.nodes.2.parameters.temp``), so the UI can point at the field a
user got wrong. Every problem in a request is reported at once.
"""

from pathlib import PurePosixPath
from typing import Any

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.catalog.catalog import Catalog, UnknownTaskError
from app.catalog.models import InputPort, TaskDefinition
from app.schemas.job import InputFiles, JobSubmitRequest, PipelineSubmitRequest

Location = tuple[str | int, ...]
UNSAFE_NAMES = frozenset({"", ".", ".."})


def make_error(
    location: Location,
    kind: str,
    message: str,
    value: Any,
) -> dict[str, Any]:
    """
    Build one error in FastAPI's validation format.

    :param location: Path of the bad field in the request body.
    :type location: Location
    :param kind: Short machine-readable error type.
    :type kind: str
    :param message: Explanation for a person.
    :type message: str
    :param value: The rejected input.
    :type value: Any
    :return: Error entry.
    :rtype: dict[str, Any]
    """
    return {"type": kind, "loc": location, "msg": message, "input": value}


def relocate_errors(
    error: ValidationError,
    location: Location,
) -> list[dict[str, Any]]:
    """
    Move parameter errors under their place in the request body.

    :param error: Errors from a task's parameter model.
    :type error: ValidationError
    :param location: Where the request object sits in the body.
    :type location: Location
    :return: Errors with full locations.
    :rtype: list[dict[str, Any]]
    """
    return [
        {**item, "loc": (*location, "parameters", *item["loc"])}
        for item in error.errors(include_url=False)
    ]


def is_plain_filename(name: str) -> bool:
    """
    Accept only a bare file name: no directories, no ``..``.

    :param name: Submitted file name.
    :type name: str
    :return: True if the name cannot point outside the workspace.
    :rtype: bool
    """
    plain = PurePosixPath(name).name == name and "\\" not in name
    return plain and name not in UNSAFE_NAMES


def filename_error(
    port: InputPort,
    name: str,
    location: Location,
) -> dict[str, Any] | None:
    """
    Check one file name against a port.

    :param port: The port being filled.
    :type port: InputPort
    :param name: Submitted file name.
    :type name: str
    :param location: Location of this file in the request body.
    :type location: Location
    :return: An error, or None if the name is acceptable.
    :rtype: dict[str, Any] | None
    """
    if not is_plain_filename(name):
        message = "Use a plain file name, without folders"
        return make_error(location, "path", message, name)
    suffix = PurePosixPath(name).suffix.lstrip(".").lower()
    if suffix not in port.formats:
        message = f"Expected one of {port.formats}"
        return make_error(location, "format", message, name)
    return None


def file_errors(
    port: InputPort,
    files: list[str],
    location: Location,
) -> list[dict[str, Any]]:
    """
    Check the files given for one known input port.

    :param port: The port being filled.
    :type port: InputPort
    :param files: File names given for it.
    :type files: list[str]
    :param location: Location of this port in the request body.
    :type location: Location
    :return: Errors found; empty if the files are acceptable.
    :rtype: list[dict[str, Any]]
    """
    errors = []
    if len(files) > 1 and not port.multiple:
        message = f"Input {port.name!r} takes one file"
        errors.append(make_error(location, "too_many_files", message, files))
    found = (
        filename_error(port, name, (*location, index))
        for index, name in enumerate(files)
    )
    return errors + [error for error in found if error]


def input_errors(
    task: TaskDefinition,
    inputs: InputFiles,
    location: Location,
) -> list[dict[str, Any]]:
    """
    Check a request's input files against the task's ports.

    :param task: Task definition.
    :type task: TaskDefinition
    :param inputs: Port name -> file names, as submitted.
    :type inputs: InputFiles
    :param location: Where the request object sits in the body.
    :type location: Location
    :return: Errors found; empty if all inputs are acceptable.
    :rtype: list[dict[str, Any]]
    """
    ports = {port.name: port for port in task.inputs}
    errors = []
    for name, files in inputs.items():
        port_location = (*location, "inputs", name)
        if name not in ports:
            message = f"{task.id} has no input {name!r}"
            errors.append(make_error(port_location, "unknown", message, name))
        else:
            errors += file_errors(ports[name], files, port_location)
    for port in task.inputs:
        if port.required and not inputs.get(port.name):
            port_location = (*location, "inputs", port.name)
            message = f"Input {port.name!r} is required"
            errors.append(make_error(port_location, "missing", message, None))
    return errors


def check_task_request(
    catalog: Catalog,
    task_id: str,
    raw_values: dict[str, Any] | None,
    inputs: InputFiles,
    location: Location,
) -> dict[str, Any]:
    """
    Check one task request and return its complete parameter values.

    :param catalog: Loaded task catalog.
    :type catalog: Catalog
    :param task_id: Requested task id.
    :type task_id: str
    :param raw_values: Values as submitted; None means none.
    :type raw_values: dict[str, Any] | None
    :param inputs: Port name -> file names, as submitted.
    :type inputs: InputFiles
    :param location: Where the request object sits in the body.
    :type location: Location
    :return: Every parameter with its final value.
    :rtype: dict[str, Any]
    :raises RequestValidationError: Listing every problem found.
    """
    try:
        task = catalog.get(task_id)
    except UnknownTaskError:
        message = f"Unknown task {task_id!r}; see GET /api/task-definitions"
        name_location = (*location, "script_name")
        error = make_error(name_location, "unknown_task", message, task_id)
        raise RequestValidationError([error]) from None
    errors = input_errors(task, inputs, location)
    try:
        values = catalog.validate_values(task_id, raw_values or {})
    except ValidationError as error:
        errors += relocate_errors(error, location)
    if errors:
        raise RequestValidationError(errors)
    return values


def validate_job_request(
    catalog: Catalog,
    request: JobSubmitRequest,
) -> JobSubmitRequest:
    """
    Return a copy of a single-job request with validated parameters.

    :param catalog: Loaded task catalog.
    :type catalog: Catalog
    :param request: Request as submitted.
    :type request: JobSubmitRequest
    :return: Request whose parameters are complete and valid.
    :rtype: JobSubmitRequest
    :raises RequestValidationError: Listing every problem found.
    """
    values = check_task_request(
        catalog,
        request.script_name,
        request.parameters,
        request.inputs,
        ("body",),
    )
    return request.model_copy(update={"parameters": values})


def validate_pipeline_request(
    catalog: Catalog,
    request: PipelineSubmitRequest,
) -> PipelineSubmitRequest:
    """
    Return a copy of a pipeline request with every node validated.

    :param catalog: Loaded task catalog.
    :type catalog: Catalog
    :param request: Request as submitted.
    :type request: PipelineSubmitRequest
    :return: Request whose nodes have complete, valid parameters.
    :rtype: PipelineSubmitRequest
    :raises RequestValidationError: Listing every bad node at once.
    """
    errors: list[dict[str, Any]] = []
    nodes = []
    for index, node in enumerate(request.nodes):
        try:
            values = check_task_request(
                catalog,
                node.script_name,
                node.parameters,
                node.inputs,
                ("body", "nodes", index),
            )
        except RequestValidationError as error:
            errors.extend(error.errors())
            continue
        nodes.append(node.model_copy(update={"parameters": values}))
    if errors:
        raise RequestValidationError(errors)
    return request.model_copy(update={"nodes": nodes})
