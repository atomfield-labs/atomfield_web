"""
Typed models of ``catalog.json``, the format a domain pack ships.

Unknown fields are rejected. In a versioned contract an unexpected
field is either a typo or a newer format, and both should stop the
platform at startup rather than be ignored.
"""

from collections import Counter
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    model_validator,
)

# Names and versions of what agents download (releases, data packs):
# they become folder names on agents' machines.
PACKAGE_NAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._+!-]{0,99}"
ENVIRONMENT_NAME_PATTERN = r"[A-Z][A-Z0-9_]{0,63}"
# Variables the agent sets for every job; a data pack may not take one.
RESERVED_ENVIRONMENT = frozenset(
    {
        "HOME",
        "LD_LIBRARY_PATH",
        "OMP_NUM_THREADS",
        "PATH",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
    }
)


class ParameterKind(StrEnum):
    """
    The kinds of value a task parameter accepts.
    """

    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"


class ContractModel(BaseModel):
    """
    Base for catalog models: immutable and strict about field names.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class Resources(ContractModel):
    """
    What one run of a task asks the scheduler for.
    """

    cpus: PositiveInt
    memory_mb: PositiveInt
    walltime_minutes: PositiveInt
    # The task runs ``cpus`` MPI processes (Quantum ESPRESSO, GROMACS)
    # rather than one process with ``cpus`` threads (xTB); schedulers
    # are asked for them differently.
    mpi: bool = False


class PlatformFlags(ContractModel):
    """
    Flags the platform fills in itself; users never see them.
    """

    job_name: str | None = None
    cpus: str | None = None


class InputPort(ContractModel):
    """
    One kind of input file a task reads.
    """

    name: str
    flag: str
    formats: list[str]
    required: bool = False
    multiple: bool = False


class OutputPort(ContractModel):
    """
    One kind of output file a task writes, found by a glob pattern.
    """

    name: str
    glob: str


class ParameterSpec(ContractModel):
    """
    One user-settable option of a task, as its script declares it.
    """

    name: str
    flag: str
    kind: ParameterKind
    default: Any = None
    choices: list[Any] | None = None
    multiple: bool = False
    required: bool = False
    help: str | None = None
    label: str | None = None
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def check_default_is_a_choice(self) -> "ParameterSpec":
        """
        Reject a default that the parameter's own choices forbid.

        :return: The validated spec.
        :rtype: ParameterSpec
        :raises ValueError: If the default is not among the choices.
        """
        outside = self.default is not None and self.default not in (
            self.choices or [self.default]
        )
        if outside:
            raise ValueError(
                f"{self.name}: default {self.default!r} is not a choice"
            )
        return self


class DataNeed(ContractModel):
    """
    A data pack a task reads (pseudopotentials, model weights...), and
    the environment variable that tells the task where it is.
    """

    name: str = Field(pattern=f"^{PACKAGE_NAME_PATTERN}$")
    version: str = Field(pattern=f"^{PACKAGE_NAME_PATTERN}$")
    env: str = Field(pattern=f"^{ENVIRONMENT_NAME_PATTERN}$")

    @model_validator(mode="after")
    def check_variable_is_free(self) -> "DataNeed":
        """
        Reject a variable the agent sets itself.

        :return: The validated need.
        :rtype: DataNeed
        :raises ValueError: If the variable is reserved.
        """
        if self.env in RESERVED_ENVIRONMENT:
            raise ValueError(f"{self.env} is set by the agent; use another")
        return self


class TaskDefinition(ContractModel):
    """
    Everything the platform needs to show, check and run one task.
    """

    id: str
    title: str
    description: str
    category: str
    module: str
    resources: Resources
    platform_flags: PlatformFlags
    inputs: list[InputPort]
    outputs: list[OutputPort]
    parameters: list[ParameterSpec]
    # Data packs the agent puts in place before the task starts.
    data: list[DataNeed] = []

    @model_validator(mode="after")
    def check_data_variables_are_unique(self) -> "TaskDefinition":
        """
        Reject two data packs handed over in the same variable.

        :return: The validated definition.
        :rtype: TaskDefinition
        :raises ValueError: If a variable is used twice.
        """
        counts = Counter(need.env for need in self.data)
        repeated = sorted(env for env, n in counts.items() if n > 1)
        if repeated:
            raise ValueError(
                f"{self.id}: data variables used twice: {repeated}"
            )
        return self

    @model_validator(mode="after")
    def check_flags_are_unique(self) -> "TaskDefinition":
        """
        Reject a task in which two entries claim the same flag.

        :return: The validated definition.
        :rtype: TaskDefinition
        :raises ValueError: If any flag appears more than once.
        """
        flags = [spec.flag for spec in self.parameters]
        flags += [port.flag for port in self.inputs]
        flags += [
            flag
            for flag in (self.platform_flags.job_name, self.platform_flags.cpus)
            if flag
        ]
        repeated = sorted(flag for flag, n in Counter(flags).items() if n > 1)
        if repeated:
            raise ValueError(f"{self.id}: flags used twice: {repeated}")
        return self


class CatalogDocument(ContractModel):
    """
    The whole ``catalog.json`` file.
    """

    # Only format 1 exists; a newer file must fail loudly, not half-load.
    format_version: Literal[1]
    tasks: list[TaskDefinition]

    @model_validator(mode="after")
    def check_ids_are_unique(self) -> "CatalogDocument":
        """
        Reject a catalog in which two tasks share an id.

        :return: The validated document.
        :rtype: CatalogDocument
        :raises ValueError: If any task id appears more than once.
        """
        counts = Counter(task.id for task in self.tasks)
        repeated = sorted(task_id for task_id, n in counts.items() if n > 1)
        if repeated:
            raise ValueError(f"Task ids used twice: {repeated}")
        return self
