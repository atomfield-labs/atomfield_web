"""
Load the task catalog once and look tasks up by id.
"""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel

from app.catalog.models import CatalogDocument, TaskDefinition
from app.catalog.parameters import build_parameter_model, validate_values


class UnknownTaskError(LookupError):
    """
    Raised when a request names a task the catalog does not contain.
    """


class Catalog:
    """
    The tasks the platform can run, loaded from one ``catalog.json``.

    Everything derived from the file (lookups, parameter models) is
    built once at load time, so a definition that cannot be validated
    fails at startup instead of on someone's first submission.
    """

    def __init__(self, document: CatalogDocument) -> None:
        """
        Index a validated catalog document.

        :param document: Parsed and validated ``catalog.json``.
        :type document: CatalogDocument
        """
        self.tasks: Mapping[str, TaskDefinition] = MappingProxyType(
            {task.id: task for task in document.tasks}
        )
        self.parameter_models: Mapping[str, type[BaseModel]] = MappingProxyType(
            {task.id: build_parameter_model(task) for task in document.tasks}
        )

    @classmethod
    def from_path(cls, path: Path) -> "Catalog":
        """
        Read and validate a ``catalog.json`` file.

        :param path: Location of the file.
        :type path: Path
        :return: Loaded catalog.
        :rtype: Catalog
        :raises pydantic.ValidationError: If the file breaks the format.
        """
        text = path.read_text(encoding="utf-8")
        return cls(CatalogDocument.model_validate_json(text))

    def get(self, task_id: str) -> TaskDefinition:
        """
        Look up one task.

        :param task_id: Task id, e.g. ``xtb_opt``.
        :type task_id: str
        :return: Its definition.
        :rtype: TaskDefinition
        :raises UnknownTaskError: If no task has this id.
        """
        if task_id not in self.tasks:
            raise UnknownTaskError(task_id)
        return self.tasks[task_id]

    def validate_values(
        self,
        task_id: str,
        raw_values: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Check one task's submitted values and fill in its defaults.

        :param task_id: Task id.
        :type task_id: str
        :param raw_values: Values as submitted.
        :type raw_values: dict[str, Any]
        :return: Every parameter with its final value.
        :rtype: dict[str, Any]
        :raises UnknownTaskError: If no task has this id.
        :raises pydantic.ValidationError: On unknown names or bad values.
        """
        self.get(task_id)
        return validate_values(self.parameter_models[task_id], raw_values)
