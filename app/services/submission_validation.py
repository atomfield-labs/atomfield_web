"""
Check submissions against the task catalog before anything is stored.

Errors use FastAPI's own 422 format, located at the exact request field
(``body.nodes.2.parameters.temp``), so the UI can point at the field a
user got wrong. Every problem in a request is reported at once.
"""

from typing import Any, TypeVar

from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.catalog.catalog import Catalog, UnknownTaskError
from app.catalog.models import InputPort, TaskDefinition
from app.core.names import is_plain_name
from app.schemas.job import (
    InputFiles,
    JobNode,
    JobSubmitRequest,
    PipelineFile,
    PipelineSubmitRequest,
)

Location = tuple[str | int, ...]
# A single job and a pipeline node are checked the same way.
TaskRequest = TypeVar("TaskRequest", JobSubmitRequest, JobNode)
PLAIN_NAME_MESSAGE = (
    "Use a plain file name, without folders or control characters"
)


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


def path_error(name: str, location: Location) -> dict[str, Any] | None:
    """
    An error for a file name the store would refuse (``..``, a folder,
    a control character), so it is refused now rather than when an
    agent asks for the file.

    :param name: Submitted file name.
    :type name: str
    :param location: Location of this name in the request body.
    :type location: Location
    :return: The error, or None if the name is plain.
    :rtype: dict[str, Any] | None
    """
    if is_plain_name(name):
        return None
    return make_error(location, "path", PLAIN_NAME_MESSAGE, name)


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
    if error := path_error(name, location):
        return error
    if not port.takes(name):
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


def with_valid_parameters(
    catalog: Catalog,
    request: TaskRequest,
    location: Location,
) -> TaskRequest:
    """
    Return a copy of a task request (a job, or a pipeline node) with
    validated parameters.

    :param catalog: Loaded task catalog.
    :type catalog: Catalog
    :param request: Request as submitted.
    :type request: TaskRequest
    :param location: Where the request object sits in the body.
    :type location: Location
    :return: Request whose parameters are complete and valid.
    :rtype: TaskRequest
    :raises RequestValidationError: Listing every problem found.
    """
    values = check_task_request(
        catalog,
        request.script_name,
        request.parameters,
        request.inputs,
        location,
    )
    return request.model_copy(update={"parameters": values})


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
    return with_valid_parameters(catalog, request, ("body",))


def attachment_errors(files: list[PipelineFile]) -> list[dict[str, Any]]:
    """
    Check the names of the files attached to a pipeline, before any of
    them is stored.

    :param files: The attachments.
    :type files: list[PipelineFile]
    :return: Errors found; empty if every name is plain.
    :rtype: list[dict[str, Any]]
    """
    found = (
        path_error(attachment.filename, ("body", "files", index, "filename"))
        for index, attachment in enumerate(files)
    )
    return [error for error in found if error]


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
    :raises RequestValidationError: Listing every bad node and file
        name at once.
    """
    errors: list[dict[str, Any]] = []
    nodes = []
    for index, node in enumerate(request.nodes):
        location = ("body", "nodes", index)
        try:
            nodes.append(with_valid_parameters(catalog, node, location))
        except RequestValidationError as error:
            errors.extend(error.errors())
    errors += attachment_errors(request.files or [])
    if errors:
        raise RequestValidationError(errors)
    return request.model_copy(update={"nodes": nodes})
