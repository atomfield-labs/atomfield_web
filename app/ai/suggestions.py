"""
Checking what a model suggests before anyone sees it, with the same
validator a real submission goes through. A made-up setting or an
out-of-range value is flagged, not hidden: the person should see that the
model got it wrong.
"""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.prompts import AiSuggestion
from app.catalog.catalog import Catalog
from app.catalog.models import ParameterKind, ParameterSpec, ParameterWidget

NOT_A_SETTING = "This is not a setting of this step."
NOT_ALLOWED = "This value isn't allowed for this setting: {why}"
BAD_MESH = "This value isn't allowed for this setting: expected three numbers."
MESH = re.compile(r"^\s*\d+\s+\d+\s+\d+\s*$")
LIST_SEPARATOR = re.compile(r"[\s,]+")


class CheckedSuggestion(BaseModel):
    """
    A suggestion after checking: what the screen shows.
    """

    setting: str
    label: str | None = None
    unit: str | None = None
    current: Any = None
    value: str
    why: str
    problem: str | None = None


def single_value(spec: ParameterSpec, text: str) -> Any:
    """
    Read one value as its setting's kind: a model gives every value as
    text, and text is left alone if it can't be read, for the validator
    to refuse.

    :param spec: The setting.
    :type spec: ParameterSpec
    :param text: The value.
    :type text: str
    :return: The value.
    :rtype: Any
    """
    if spec.kind is ParameterKind.STRING:
        return text
    try:
        return json.loads(text.strip().lower())
    except ValueError:
        return text


def parsed_value(spec: ParameterSpec, text: str) -> Any:
    """
    Read a suggested value as its setting's kind.

    :param spec: The setting.
    :type spec: ParameterSpec
    :param text: The value.
    :type text: str
    :return: The value, or a list for a setting that takes many.
    :rtype: Any
    """
    if not spec.multiple:
        return single_value(spec, text)
    pieces = (piece for piece in LIST_SEPARATOR.split(text.strip()))
    return [single_value(spec, piece) for piece in pieces if piece]


def problem_with(
    catalog: Catalog,
    task_id: str,
    spec: ParameterSpec,
    text: str,
    current: Mapping[str, Any],
) -> str | None:
    """
    What is wrong with a suggested value, if anything.

    :param catalog: The catalog of the job's run.
    :type catalog: Catalog
    :param task_id: The task.
    :type task_id: str
    :param spec: The setting.
    :type spec: ParameterSpec
    :param text: The value.
    :type text: str
    :param current: The job's other values.
    :type current: Mapping[str, Any]
    :return: The problem, or None if it would be accepted.
    :rtype: str | None
    """
    if spec.widget is ParameterWidget.MESH and not MESH.match(text):
        return BAD_MESH
    values = {**current, spec.name: parsed_value(spec, text)}
    try:
        catalog.validate_values(task_id, values)
    except ValidationError as error:
        for item in error.errors():
            if spec.name in item["loc"]:
                return NOT_ALLOWED.format(why=item["msg"])
    return None


def check_one(
    item: AiSuggestion,
    catalog: Catalog,
    task_id: str,
    current: Mapping[str, Any],
) -> CheckedSuggestion:
    """
    Check one suggestion. The unit and the current value come from the
    catalog and the job, not from the model.

    :param item: What the model suggested.
    :type item: AiSuggestion
    :param catalog: The catalog of the job's run.
    :type catalog: Catalog
    :param task_id: The task.
    :type task_id: str
    :param current: The job's values: setting name -> value.
    :type current: Mapping[str, Any]
    :return: The suggestion, with any problem noted.
    :rtype: CheckedSuggestion
    """
    specs = {spec.name: spec for spec in catalog.get(task_id).parameters}
    spec = specs.get(item.setting)
    fields = item.model_dump()
    if spec is None:
        return CheckedSuggestion(**fields, problem=NOT_A_SETTING)
    return CheckedSuggestion(
        **fields,
        label=spec.label,
        unit=spec.unit,
        current=current.get(item.setting),
        problem=problem_with(catalog, task_id, spec, item.value, current),
    )


def check_suggestions(
    suggestions: Sequence[AiSuggestion],
    catalog: Catalog,
    task_id: str,
    current: Mapping[str, Any],
) -> list[CheckedSuggestion]:
    """
    Check each suggestion against the task's catalog entry.

    :param suggestions: What the model suggested.
    :type suggestions: Sequence[AiSuggestion]
    :param catalog: The catalog of the job's run.
    :type catalog: Catalog
    :param task_id: The task.
    :type task_id: str
    :param current: The job's values: setting name -> value.
    :type current: Mapping[str, Any]
    :return: The suggestions, with any problem noted.
    :rtype: list[CheckedSuggestion]
    """
    return [check_one(item, catalog, task_id, current) for item in suggestions]
