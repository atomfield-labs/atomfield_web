"""
Tests for the task contract: loading, validation and command building.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.catalog.argv import Invocation, build_argv
from app.catalog.catalog import Catalog, UnknownTaskError
from app.catalog.models import CatalogDocument

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalog.json"
REAL_CATALOG = Path(__file__).resolve().parents[1] / "scripts_repo"
REAL_CATALOG = REAL_CATALOG / "catalog.json"
PYTHON = "/env/bin/python"


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    """
    Load the fixture catalog.

    :return: Catalog with the toy tasks.
    :rtype: Catalog
    """
    return Catalog.from_path(FIXTURE)


def fixture_document() -> dict[str, Any]:
    """
    Read the fixture as plain data, to break it on purpose.

    :return: Parsed fixture JSON.
    :rtype: dict[str, Any]
    """
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def error_fields(error: ValidationError) -> set[str]:
    """
    Name the fields a validation error complains about.

    :param error: Raised validation error.
    :type error: ValidationError
    :return: First element of each error location.
    :rtype: set[str]
    """
    return {str(item["loc"][0]) for item in error.errors()}


@pytest.mark.skipif(not REAL_CATALOG.exists(), reason="no scripts_repo")
def test_the_real_catalog_loads():
    """
    afscripts' exported catalog satisfies the platform's models.
    """
    loaded = Catalog.from_path(REAL_CATALOG)
    assert "xtb_opt" in loaded.tasks
    assert len(loaded.tasks) == 7


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        (lambda doc: doc.update(format_version=2), "format_version"),
        (lambda doc: doc["tasks"][0].update(colour="red"), "colour"),
        (
            lambda doc: doc["tasks"][0]["parameters"][1].update(flag="-charge"),
            "flags used twice",
        ),
        (
            lambda doc: doc["tasks"][0]["parameters"][4].update(default="x"),
            "is not a choice",
        ),
        (
            lambda doc: doc["tasks"][1].update(id="toy_opt"),
            "ids used twice",
        ),
    ],
)
def test_broken_catalogs_are_rejected(break_it, message: str):
    """
    Future formats, unknown fields, reused flags, impossible defaults
    and repeated ids all stop loading.

    :param break_it: Mutates the fixture document.
    :type break_it: Callable[[dict], None]
    :param message: Text expected in the error.
    :type message: str
    """
    document = fixture_document()
    break_it(document)
    with pytest.raises(ValidationError, match=message):
        CatalogDocument.model_validate(document)


def test_validation_fills_in_defaults(catalog: Catalog):
    """
    Omitted parameters get their defaults, so a job records every value.

    :param catalog: Fixture catalog.
    :type catalog: Catalog
    """
    values = catalog.validate_values("toy_opt", {"charge": -1})
    assert values == {
        "charge": -1,
        "temp": 300.0,
        "gfnff": False,
        "keep": True,
        "optlevel": "normal",
        "gfn": 2,
        "solvent": None,
    }


def test_validation_names_every_bad_field(catalog: Catalog):
    """
    Unknown names, wrong types, bad choices and out-of-range values are
    each reported against the field's own name.

    :param catalog: Fixture catalog.
    :type catalog: Catalog
    """
    submitted = {
        "pipeline_id": "smuggled",
        "charge": "two",
        "optlevel": "vtight",
        "temp": -5,
        "gfn": 3,
    }
    with pytest.raises(ValidationError) as raised:
        catalog.validate_values("toy_opt", submitted)
    assert error_fields(raised.value) == set(submitted)


def test_required_parameters_and_unknown_tasks(catalog: Catalog):
    """
    A required parameter must be given; an unknown task is refused.

    :param catalog: Fixture catalog.
    :type catalog: Catalog
    """
    with pytest.raises(ValidationError) as raised:
        catalog.validate_values("toy_network", {})
    assert error_fields(raised.value) == {"method"}
    with pytest.raises(UnknownTaskError):
        catalog.validate_values("no_such_task", {})


def test_parameter_names_cannot_clash_with_pydantic(catalog: Catalog):
    """
    A parameter called ``copy`` validates like any other.

    :param catalog: Fixture catalog.
    :type catalog: Catalog
    """
    values = catalog.validate_values(
        "toy_network",
        {"method": "smiles", "copy": "b"},
    )
    assert values["copy"] == "b"


def test_build_argv_renders_the_exact_command(catalog: Catalog):
    """
    Inputs, platform flags and parameters appear in a fixed order, and
    switches equal to their default are left out.

    :param catalog: Fixture catalog.
    :type catalog: Catalog
    """
    task = catalog.get("toy_opt")
    values = catalog.validate_values(
        "toy_opt",
        {"charge": 1, "gfnff": True, "optlevel": "tight"},
    )
    invocation = Invocation(
        values=values,
        inputs={"structure": ["in/water.xyz"]},
        job_name="job42",
        cpus=4,
    )

    argv = build_argv(task, invocation, PYTHON)

    assert argv == [
        PYTHON, "-u", "-m", "toy.opt_driver",
        "-i", "in/water.xyz",
        "-JOBNAME", "job42",
        "-parallel", "4",
        "-charge", "1",
        "-temp", "300.0",
        "-gfnff",
        "-optlevel", "tight",
        "-gfn", "2",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("keep", "expected"),
    [(True, False), (False, True)],
)
def test_switches_are_passed_only_when_they_change_something(
    catalog: Catalog,
    keep: bool,
    expected: bool,
):
    """
    A ``store_false`` switch (default True) appears only for False.

    :param catalog: Fixture catalog.
    :type catalog: Catalog
    :param keep: Value requested for the switch.
    :type keep: bool
    :param expected: Whether its flag should appear.
    :type expected: bool
    """
    values = catalog.validate_values("toy_opt", {"keep": keep})
    invocation = Invocation(values, {}, "job", 1)
    argv = build_argv(catalog.get("toy_opt"), invocation, PYTHON)
    assert ("-nokeep" in argv) is expected


def test_list_inputs_and_list_parameters(catalog: Catalog):
    """
    List ports and list parameters put all values after one flag; a
    single-file port refuses several files.

    :param catalog: Fixture catalog.
    :type catalog: Catalog
    """
    task = catalog.get("toy_network")
    values = catalog.validate_values(
        "toy_network",
        {"method": "smiles", "tags": ["x", "y"]},
    )
    inputs = {"trajectories": ["a.xyz", "b.xyz"], "reference": ["r.xyz"]}

    argv = build_argv(task, Invocation(values, inputs, "net", 1), PYTHON)

    assert argv[4:10] == ["-i", "a.xyz", "b.xyz", "-ref", "r.xyz", "-JOBNAME"]
    assert argv[-5:] == ["-tags", "x", "y", "-copy", "a"]
    too_many = {"reference": ["r1.xyz", "r2.xyz"]}
    with pytest.raises(ValueError, match="takes one file"):
        build_argv(task, Invocation(values, too_many, "net", 1), PYTHON)


def test_unvalidated_bookkeeping_never_reaches_the_command(catalog: Catalog):
    """
    Only declared parameters are rendered, even if a caller passes
    extra keys straight to ``build_argv``.

    :param catalog: Fixture catalog.
    :type catalog: Catalog
    """
    values = {"pipeline_id": "secret_pipeline", "charge": 0}
    argv = build_argv(
        catalog.get("toy_opt"),
        Invocation(values, {}, "job", 1),
        PYTHON,
    )
    assert "secret_pipeline" not in argv
    assert "-pipeline_id" not in argv
