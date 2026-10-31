"""
Turn a task definition plus validated values into an exact command.

Only flags declared in the definition can reach the command (an
allow-list), so platform bookkeeping such as ``pipeline_id`` can never
leak in. The result is a list of arguments for ``subprocess``; no shell
ever parses it, so spaces or quotes in values are harmless.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.catalog.models import (
    InputPort,
    ParameterKind,
    ParameterSpec,
    PlatformFlags,
    TaskDefinition,
)

UNBUFFERED = "-u"
RUN_CODE = "-c"
# Compiled scripts cannot start with ``python -m``, which needs code it
# can read. Every script has ``main``; ``module`` is checked by the
# catalog's pattern, since it lands inside this line of code.
RUN_MAIN = "import sys; from {module} import main; sys.exit(main())"


@dataclass(frozen=True, slots=True)
class Invocation:
    """
    One run of a task: what the user chose plus what the platform sets.

    :param values: Validated parameter values, keyed by name.
    :type values: Mapping[str, Any]
    :param inputs: Input port name -> file paths for that port.
    :type inputs: Mapping[str, Sequence[str]]
    :param job_name: Name the script uses for its output files.
    :type job_name: str
    :param cpus: Cores the run may use.
    :type cpus: int
    """

    values: Mapping[str, Any]
    inputs: Mapping[str, Sequence[str]]
    job_name: str
    cpus: int


def parameter_tokens(spec: ParameterSpec, value: Any) -> list[str]:
    """
    Render one parameter as command-line tokens.

    A value-less flag (``store_true`` or ``store_false``) is passed only
    when the wanted value differs from the default, which is right for
    both. None means "let the script use its own default".

    :param spec: Parameter specification.
    :type spec: ParameterSpec
    :param value: Validated value.
    :type value: Any
    :return: Zero or more tokens.
    :rtype: list[str]
    """
    if value is None:
        return []
    if spec.kind is ParameterKind.BOOLEAN:
        return [spec.flag] if value != spec.default else []
    if spec.multiple:
        return [spec.flag, *map(str, value)] if value else []
    return [spec.flag, str(value)]


def input_tokens(port: InputPort, paths: Sequence[str]) -> list[str]:
    """
    Render one input port's files as command-line tokens.

    :param port: Input port.
    :type port: InputPort
    :param paths: Files for this port.
    :type paths: Sequence[str]
    :return: Zero or more tokens.
    :rtype: list[str]
    :raises ValueError: If a single-file port is given several files.
    """
    if not paths:
        return []
    if len(paths) > 1 and not port.multiple:
        raise ValueError(f"Input {port.name!r} takes one file")
    return [port.flag, *paths]


def platform_tokens(flags: PlatformFlags, invocation: Invocation) -> list[str]:
    """
    Render the flags the platform fills in itself.

    :param flags: The task's platform-managed flags.
    :type flags: PlatformFlags
    :param invocation: The run being started.
    :type invocation: Invocation
    :return: Zero or more tokens.
    :rtype: list[str]
    """
    tokens = []
    if flags.job_name:
        tokens += [flags.job_name, invocation.job_name]
    if flags.cpus:
        tokens += [flags.cpus, str(invocation.cpus)]
    return tokens


def build_argv(
    task: TaskDefinition,
    invocation: Invocation,
    python_bin: str,
) -> list[str]:
    """
    Build the exact command that runs one task.

    :param task: Task definition.
    :type task: TaskDefinition
    :param invocation: Validated values, inputs and platform values.
    :type invocation: Invocation
    :param python_bin: Interpreter of the pack's environment.
    :type python_bin: str
    :return: Argument list for ``subprocess``.
    :rtype: list[str]
    :raises ValueError: If a single-file port is given several files.
    """
    start = RUN_MAIN.format(module=task.module)
    argv = [python_bin, UNBUFFERED, RUN_CODE, start]
    for port in task.inputs:
        argv += input_tokens(port, invocation.inputs.get(port.name, ()))
    argv += platform_tokens(task.platform_flags, invocation)
    for spec in task.parameters:
        argv += parameter_tokens(spec, invocation.values.get(spec.name))
    return argv
