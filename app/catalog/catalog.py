"""
Load the task catalog once and look tasks up by id.
"""

from collections.abc import Collection, Mapping
from copy import copy
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.catalog.models import (
    CatalogDocument,
    PipelineTemplate,
    TaskDefinition,
    Workflow,
)
from app.catalog.parameters import build_parameter_model, validate_values

# What a mapping holds: tasks, templates or workflows.
Item = TypeVar("Item")


class UnknownTaskError(LookupError):
    """
    Raised when a request names a task the catalog does not contain.
    """


def accepts_file(task: TaskDefinition, filename: str) -> bool:
    """
    Whether one of a task's inputs takes a file of this type.

    :param task: The task.
    :type task: TaskDefinition
    :param filename: The file's name.
    :type filename: str
    :return: True if an input takes it (``InputPort.takes``).
    :rtype: bool
    """
    return any(port.takes(filename) for port in task.inputs)


def only_named(
    items: Mapping[str, Item], names: Collection[str]
) -> Mapping[str, Item]:
    """
    The entries of a mapping with these names, read-only.

    :param items: The mapping.
    :type items: Mapping[str, Item]
    :param names: The names to keep.
    :type names: Collection[str]
    :return: The kept entries.
    :rtype: Mapping[str, Item]
    """
    kept = {name: item for name, item in items.items() if name in names}
    return MappingProxyType(kept)


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
        self.templates: Mapping[str, PipelineTemplate] = MappingProxyType(
            {template.id: template for template in document.pipelines}
        )
        self.workflows: Mapping[str, Workflow] = MappingProxyType(
            {workflow.id: workflow for workflow in document.workflows}
        )
        self.workflow_by_task: Mapping[str, str] = MappingProxyType(
            {
                task: workflow.id
                for workflow in document.workflows
                for task in workflow.tasks
            }
        )
        for template in document.pipelines:
            self.check_template(template)

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

    def limited_to(self, workflow_ids: Collection[str]) -> "Catalog":
        """
        This catalog as someone given only these workflows sees it:
        anything outside them is simply not there, so listing a task
        and refusing it cannot disagree. Parameter models stay shared:
        every lookup goes through ``tasks`` first.

        :param workflow_ids: The workflows; unknown ids are ignored.
        :type workflow_ids: Collection[str]
        :return: The limited catalog.
        :rtype: Catalog
        """
        chosen = only_named(self.workflows, workflow_ids)
        workflows = chosen.values()
        tasks = {name for item in workflows for name in item.tasks}
        templates = {name for item in workflows for name in item.pipelines}
        limited = copy(self)
        limited.workflows = chosen
        limited.tasks = only_named(self.tasks, tasks)
        limited.templates = only_named(self.templates, templates)
        return limited

    def workflow_of(self, task_id: str) -> str | None:
        """
        The package a task belongs to, whose file it runs from.

        :param task_id: Task id.
        :type task_id: str
        :return: The workflow's id; None in a catalog from before
            workflows.
        :rtype: str | None
        """
        return self.workflow_by_task.get(task_id)

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

    def check_template(self, template: PipelineTemplate) -> None:
        """
        Check a pipeline template against the tasks: each step names a
        task of this catalog with valid parameter values, and each
        structure a step reads fits one of that task's inputs.

        :param template: A template of this catalog.
        :type template: PipelineTemplate
        :raises ValueError: On the first problem, naming the step.
        """
        filenames = {item.key: item.filename for item in template.structures}
        for step in template.steps:
            where = f"Template {template.id}, step {step.key}"
            if step.task not in self.tasks:
                raise ValueError(f"{where}: unknown task {step.task}")
            try:
                self.validate_values(step.task, step.parameters)
            except ValidationError as error:
                raise ValueError(f"{where}: {error}") from error
            for key in set(step.after) & set(filenames):
                if not accepts_file(self.tasks[step.task], filenames[key]):
                    raise ValueError(
                        f"{where}: no input takes {filenames[key]}"
                    )
