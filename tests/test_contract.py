"""
Contract test: every command ``build_argv`` produces for the real
catalog is accepted by the real script's parser, with the intended
values.

The platform never imports a pack's code, so the parsing happens in the
pack's own interpreter, in a subprocess. Skipped where the pack or its
environment is missing (CI today; the pack's image after Phase 6).
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.catalog.argv import Invocation, build_argv
from app.catalog.catalog import Catalog
from app.catalog.models import ParameterKind, ParameterSpec, TaskDefinition
from app.core.config import settings

PACK_ROOT = Path(__file__).resolve().parents[1] / "scripts_repo"
REAL_CATALOG = PACK_ROOT / "catalog.json"
PROBE_CPUS = 3
PARSE_SCRIPT = """
import importlib, json, sys
results = []
for request in json.load(sys.stdin):
    parser = importlib.import_module(request["module"]).get_parser()
    dests = {f: a.dest for a in parser._actions for f in a.option_strings}
    values = vars(parser.parse_args(request["args"]))
    results.append({"values": values, "dests": dests})
print("\\n" + json.dumps(results, default=str))
"""

pytestmark = pytest.mark.skipif(
    not (
        REAL_CATALOG.exists()
        and settings.CHEMISTRY_PYTHON_BIN
        and Path(settings.CHEMISTRY_PYTHON_BIN).exists()
    ),
    reason="needs scripts_repo and the chemistry interpreter",
)


def probe_value(spec: ParameterSpec) -> Any:
    """
    Pick a valid value that differs from the default where possible, so
    a dropped or misspelled flag cannot pass unnoticed.

    :param spec: Parameter specification.
    :type spec: ParameterSpec
    :return: Value to send.
    :rtype: Any
    """
    if spec.kind is ParameterKind.BOOLEAN:
        return not spec.default
    if spec.choices:
        others = [choice for choice in spec.choices if choice != spec.default]
        return (others or spec.choices)[0]
    if spec.kind is ParameterKind.INTEGER:
        single = (spec.default or spec.minimum or 0) + 1
    elif spec.kind is ParameterKind.NUMBER:
        single = (spec.default or spec.minimum or 0.0) + 0.5
    else:
        single = "probe"
    return [single, single] if spec.multiple else single


def probe_inputs(task: TaskDefinition) -> dict[str, list[str]]:
    """
    Invent one file per input port (two for list ports).

    :param task: Task definition.
    :type task: TaskDefinition
    :return: Port name -> file names.
    :rtype: dict[str, list[str]]
    """
    return {
        port.name: [f"{port.name}_{n}.{port.formats[0]}" for n in (1, 2)][
            : 2 if port.multiple else 1
        ]
        for port in task.inputs
    }


def parse_with_real_parsers(requests: list[dict]) -> list[dict]:
    """
    Parse argument lists with each task's own parser, in the pack's
    interpreter.

    :param requests: ``{"module": ..., "args": [...]}`` per task.
    :type requests: list[dict]
    :return: Parsed values and flag -> dest map, per request.
    :rtype: list[dict]
    """
    environment = {**os.environ, "PYTHONPATH": str(PACK_ROOT / "src")}
    completed = subprocess.run(
        [settings.CHEMISTRY_PYTHON_BIN, "-c", PARSE_SCRIPT],
        input=json.dumps(requests),
        capture_output=True,
        text=True,
        env=environment,
        cwd=PACK_ROOT,
        check=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_every_task_round_trips_through_its_real_parser():
    """
    Values, input files and platform flags survive the trip intact.
    """
    catalog = Catalog.from_path(REAL_CATALOG)
    plans = []
    for task in catalog.tasks.values():
        probes = {spec.name: probe_value(spec) for spec in task.parameters}
        values = catalog.validate_values(task.id, probes)
        inputs = probe_inputs(task)
        invocation = Invocation(values, inputs, task.id, PROBE_CPUS)
        args = build_argv(task, invocation, "python")[4:]
        plans.append((task, values, inputs, args))

    requests = [{"module": t.module, "args": a} for t, _, _, a in plans]
    parsed = parse_with_real_parsers(requests)

    for (task, values, inputs, _), result in zip(plans, parsed, strict=True):
        got, dests = result["values"], result["dests"]
        for spec in task.parameters:
            assert got[spec.name] == values[spec.name], (task.id, spec.name)
        for port in task.inputs:
            expected = inputs[port.name]
            got_files = got[dests[port.flag]]
            wanted = expected if port.multiple else expected[0]
            assert got_files == wanted, (task.id, port.name)
        flags = task.platform_flags
        assert got[dests[flags.job_name]] == task.id
        if flags.cpus:
            assert got[dests[flags.cpus]] == PROBE_CPUS
