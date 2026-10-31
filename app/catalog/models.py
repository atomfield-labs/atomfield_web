"""
Typed models of ``catalog.json``, the format a domain pack ships.

Unknown fields are rejected. In a versioned contract an unexpected
field is either a typo or a newer format, and both should stop the
platform at startup rather than be ignored.
"""

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    model_validator,
)

from app.core.names import given_twice

# Names and versions of what agents download (releases, data packs):
# they become folder names on agents' machines.
PACKAGE_NAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._+!-]{0,99}"
ENVIRONMENT_NAME_PATTERN = r"[A-Z][A-Z0-9_]{0,63}"
# A template's node keys become job folder names on agents' machines.
NODE_KEY_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
FILE_NAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}"
# A template's example structures travel inside the catalog.
MAX_TEMPLATE_STRUCTURE_CHARS = 64 * 1024
# A workflow's id is stored with what each lab and person may use.
WORKFLOW_ID_LENGTH = 64
WORKFLOW_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
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

    def takes(self, filename: str) -> bool:
        """
        Whether this input takes a file of this name: its type is its
        extension, in any case (a name without one has no type).

        :param filename: The file's name.
        :type filename: str
        :return: True if its extension is one of ``formats``.
        :rtype: bool
        """
        extension = PurePosixPath(filename).suffix.lstrip(".").lower()
        return extension in self.formats


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
        if repeated := given_twice(need.env for need in self.data):
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
        if repeated := given_twice(flags):
            raise ValueError(f"{self.id}: flags used twice: {repeated}")
        return self


class TemplateStructure(ContractModel):
    """
    An example structure a pipeline template starts from, its text
    included, so the template is complete inside the catalog.
    """

    key: str = Field(pattern=f"^{NODE_KEY_PATTERN}$")
    filename: str = Field(pattern=f"^{FILE_NAME_PATTERN}$")
    content: str = Field(max_length=MAX_TEMPLATE_STRUCTURE_CHARS)


class TemplateStep(ContractModel):
    """
    One step of a pipeline template: a catalog task, the nodes whose
    results it reads, and the parameter values that differ from the
    task's defaults.
    """

    key: str = Field(pattern=f"^{NODE_KEY_PATTERN}$")
    task: str
    label: str
    after: list[str] = []
    parameters: dict[str, Any] = {}


class PipelineTemplate(ContractModel):
    """
    A ready-made pipeline the editor offers. Its steps are listed in
    the order they run, and a step may follow only structures and
    steps listed before it, so a template cannot loop.
    """

    id: str
    title: str
    description: str
    structures: list[TemplateStructure] = []
    steps: list[TemplateStep] = Field(min_length=1)

    @model_validator(mode="after")
    def check_steps_follow_earlier_nodes(self) -> "PipelineTemplate":
        """
        Reject a step that follows a node not listed before it, and
        two nodes sharing a key.

        :return: The validated template.
        :rtype: PipelineTemplate
        :raises ValueError: On the first such step or key.
        """
        earlier = [structure.key for structure in self.structures]
        for step in self.steps:
            later = sorted(set(step.after) - set(earlier))
            if later:
                raise ValueError(
                    f"Template {self.id}: {step.key} follows {later}, "
                    "not listed before it"
                )
            earlier.append(step.key)
        if repeated := given_twice(earlier):
            raise ValueError(f"Template {self.id}: keys used twice: {repeated}")
        return self


class Workflow(ContractModel):
    """
    A package a lab can be given: a named bundle of tasks and ready-made
    pipelines, and the file those tasks run from.
    """

    id: str = Field(pattern=WORKFLOW_ID_PATTERN, max_length=WORKFLOW_ID_LENGTH)
    title: str
    description: str
    tasks: list[str]
    pipelines: list[str] = []


class CatalogDocument(ContractModel):
    """
    The whole ``catalog.json`` file: the tasks, the ready-made pipelines
    built from them, and the workflows that bundle both. Catalogs from
    before workflows have none.
    """

    # Only format 1 exists; a newer file must fail loudly, not half-load.
    format_version: Literal[1]
    tasks: list[TaskDefinition]
    pipelines: list[PipelineTemplate] = []
    workflows: list[Workflow] = []

    @model_validator(mode="after")
    def check_ids_are_unique(self) -> "CatalogDocument":
        """
        Reject a catalog in which two tasks share an id.

        :return: The validated document.
        :rtype: CatalogDocument
        :raises ValueError: If any task id appears more than once.
        """
        if repeated := given_twice(task.id for task in self.tasks):
            raise ValueError(f"Task ids used twice: {repeated}")
        return self

    @model_validator(mode="after")
    def check_template_ids_are_unique(self) -> "CatalogDocument":
        """
        Reject a catalog in which two pipeline templates share an id.

        :return: The validated document.
        :rtype: CatalogDocument
        :raises ValueError: If any template id appears more than once.
        """
        ids = (template.id for template in self.pipelines)
        if repeated := given_twice(ids):
            raise ValueError(f"Template ids used twice: {repeated}")
        return self

    @model_validator(mode="after")
    def check_workflow_ids_are_unique(self) -> "CatalogDocument":
        """
        Reject a catalog in which two workflows share an id.

        :return: The validated document.
        :rtype: CatalogDocument
        :raises ValueError: If any workflow id appears more than once.
        """
        ids = (workflow.id for workflow in self.workflows)
        if repeated := given_twice(ids):
            raise ValueError(f"Workflow ids used twice: {repeated}")
        return self

    @model_validator(mode="after")
    def check_workflows_name_what_exists(self) -> "CatalogDocument":
        """
        Reject a workflow naming a task or pipeline the catalog lacks.

        :return: The validated document.
        :rtype: CatalogDocument
        :raises ValueError: On the first such workflow.
        """
        tasks = {task.id for task in self.tasks}
        pipelines = {template.id for template in self.pipelines}
        for workflow in self.workflows:
            unknown = set(workflow.tasks) - tasks
            unknown |= set(workflow.pipelines) - pipelines
            if unknown:
                raise ValueError(
                    f"Workflow {workflow.id} names unknown {sorted(unknown)}"
                )
        return self

    @model_validator(mode="after")
    def check_pipelines_fit_their_workflows(self) -> "CatalogDocument":
        """
        Reject a workflow holding a pipeline without all of its tasks:
        someone given it could open the pipeline but not run it.

        :return: The validated document.
        :rtype: CatalogDocument
        :raises ValueError: On the first such pipeline.
        """
        templates = {template.id: template for template in self.pipelines}
        for workflow in self.workflows:
            for name in workflow.pipelines:
                needed = {step.task for step in templates[name].steps}
                if missing := sorted(needed - set(workflow.tasks)):
                    raise ValueError(
                        f"Workflow {workflow.id}: {name} also needs {missing}"
                    )
        return self

    @model_validator(mode="after")
    def check_workflows_hold_each_once(self) -> "CatalogDocument":
        """
        Reject a task or pipeline in two workflows: a job could not say
        which package's file it runs from.

        :return: The validated document.
        :rtype: CatalogDocument
        :raises ValueError: On the first such id.
        """
        tasks = (name for item in self.workflows for name in item.tasks)
        pipes = (name for item in self.workflows for name in item.pipelines)
        for held in (tasks, pipes):
            if repeated := given_twice(held):
                raise ValueError(f"In two workflows: {repeated}")
        return self

    @model_validator(mode="after")
    def check_workflows_leave_nothing_out(self) -> "CatalogDocument":
        """
        Reject workflows that leave a task or pipeline out: only the
        platform's owner could ever use it.

        :return: The validated document.
        :rtype: CatalogDocument
        :raises ValueError: If anything is in no workflow.
        """
        if not self.workflows:
            return self
        everything = {task.id for task in self.tasks}
        everything |= {template.id for template in self.pipelines}
        held = {name for item in self.workflows for name in item.tasks}
        held |= {name for item in self.workflows for name in item.pipelines}
        if left_out := sorted(everything - held):
            raise ValueError(f"In no workflow: {left_out}")
        return self
