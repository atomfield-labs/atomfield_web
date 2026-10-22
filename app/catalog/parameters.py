"""
Validate user-supplied parameter values against a task definition.

One Pydantic model is built per task from its parameter specs, so a bad
value gets the same precise, field-by-field error as any other request
field. Defaults are filled in, so a stored job records every value it
ran with.
"""

from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.fields import FieldInfo

from app.catalog.models import ParameterKind, ParameterSpec, TaskDefinition

KIND_TYPES = MappingProxyType(
    {
        ParameterKind.BOOLEAN: bool,
        ParameterKind.INTEGER: int,
        ParameterKind.NUMBER: float,
        ParameterKind.STRING: str,
    }
)


def value_type(spec: ParameterSpec) -> Any:
    """
    Choose the Python type a parameter's value must have.

    :param spec: Parameter specification.
    :type spec: ParameterSpec
    :return: A type such as ``int``, ``Literal["a", "b"]`` or a list.
    :rtype: Any
    """
    if spec.choices:
        single = Literal[tuple(spec.choices)]
    else:
        single = KIND_TYPES[spec.kind]
    value = list[single] if spec.multiple else single
    if spec.default is None and not spec.required:
        return value | None
    return value


def field_definition(spec: ParameterSpec) -> tuple[Any, FieldInfo]:
    """
    Describe one parameter as a Pydantic field.

    The field is looked up by its alias, the parameter's name, so a
    pack may name a parameter ``json`` or ``copy`` without clashing
    with ``BaseModel``'s own attributes.

    :param spec: Parameter specification.
    :type spec: ParameterSpec
    :return: Annotation and field information for ``create_model``.
    :rtype: tuple[Any, FieldInfo]
    """
    limits = {} if spec.multiple else {"ge": spec.minimum, "le": spec.maximum}
    default = ... if spec.required else spec.default
    field = Field(default, alias=spec.name, description=spec.help, **limits)
    return value_type(spec), field


def build_parameter_model(task: TaskDefinition) -> type[BaseModel]:
    """
    Build the model that validates one task's parameter values.

    :param task: Task definition.
    :type task: TaskDefinition
    :return: Model class; unknown parameter names are rejected.
    :rtype: type[BaseModel]
    """
    fields = {
        f"field_{index}": field_definition(spec)
        for index, spec in enumerate(task.parameters)
    }
    return create_model(
        f"{task.id}_parameters",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def validate_values(
    model: type[BaseModel],
    raw_values: dict[str, Any],
) -> dict[str, Any]:
    """
    Check submitted values and fill in defaults.

    :param model: Model built by ``build_parameter_model``.
    :type model: type[BaseModel]
    :param raw_values: Values as submitted, keyed by parameter name.
    :type raw_values: dict[str, Any]
    :return: Every parameter with its validated or default value.
    :rtype: dict[str, Any]
    :raises pydantic.ValidationError: On unknown names or bad values.
    """
    return model.model_validate(raw_values).model_dump(by_alias=True)
