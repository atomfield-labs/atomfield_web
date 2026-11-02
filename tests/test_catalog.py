"""
Tests for the task contract: loading, validation and command building.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.catalog.argv import RUN_MAIN, Invocation, build_argv
from app.catalog.catalog import Catalog, UnknownTaskError
from app.catalog.models import CatalogDocument, InputPort, TaskDefinition

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
    assert {"xtb_opt", "ahc_scf", "qe_phonon"} <= set(loaded.tasks)
    assert {"nanoreactor", "wannier90"} <= set(loaded.workflows)


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
        (
            lambda doc: doc["tasks"][0].update(module="toy; import os"),
            "should match pattern",
        ),
        (
            lambda doc: doc["tasks"][0]["parameters"][0].update(widget="dial"),
            "widget",
        ),
        (
            lambda doc: doc["tasks"][0]["parameters"][0].update(step=0),
            "greater than 0",
        ),
        (
            lambda doc: doc["tasks"][0]["parameters"][0].update(
                show_when={"no_such_parameter": 1}
            ),
            "can't happen",
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


@pytest.mark.skipif(not REAL_CATALOG.exists(), reason="no scripts_repo")
def test_the_real_templates_fit_the_real_tasks():
    """
    afscripts' ready-made pipelines pass the checks a release must
    pass: real tasks, valid values, structures their steps can read.
    """
    templates = Catalog.from_path(REAL_CATALOG).templates
    assert {"ahc", "nanoreactor", "nanoreactor_modular"} <= set(templates)
    assert templates["ahc"].steps[0].parameters["magnetization"] == "Fe=0.5"


def toy_template(document: dict[str, Any]) -> dict[str, Any]:
    """
    The fixture's one template, to break it on purpose.

    :param document: The fixture as plain data.
    :type document: dict[str, Any]
    :return: The template inside it.
    :rtype: dict[str, Any]
    """
    return document["pipelines"][0]


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        (
            lambda doc: toy_template(doc)["steps"][0].update(task="toy_md"),
            "unknown task toy_md",
        ),
        (
            lambda doc: toy_template(doc)["steps"][0].update(
                parameters={"charge": "one"}
            ),
            "step opt",
        ),
        (
            lambda doc: toy_template(doc)["structures"][0].update(
                filename="water.cif"
            ),
            "no input takes water.cif",
        ),
        (
            lambda doc: toy_template(doc)["steps"][0].update(after=["network"]),
            "not listed before it",
        ),
        (
            lambda doc: toy_template(doc)["steps"][1].update(key="opt"),
            "keys used twice",
        ),
    ],
    ids=["task", "value", "file", "loop", "key"],
)
def test_broken_templates_are_rejected(break_it, message: str):
    """
    A template whose step names an unknown task or a bad value, reads
    a structure no input takes, follows a later step or reuses a key
    stops the catalog from loading, and so a release from publishing.

    :param break_it: Mutates the fixture document.
    :type break_it: Callable[[dict], None]
    :param message: Text expected in the error.
    :type message: str
    """
    document = fixture_document()
    del document["workflows"]
    break_it(document)
    with pytest.raises(ValueError, match=message):
        Catalog(CatalogDocument.model_validate(document))


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        (
            lambda doc: doc["workflows"][1].update(id="toy_chain"),
            "Workflow ids used twice",
        ),
        (
            lambda doc: doc["workflows"][1].update(id="../toy"),
            "should match pattern",
        ),
        (
            lambda doc: doc["workflows"][1].update(tasks=["toy_md"]),
            "names unknown",
        ),
        (
            lambda doc: doc["workflows"][1].update(pipelines=["toy_md"]),
            "names unknown",
        ),
        (
            lambda doc: doc["workflows"][1].update(pipelines=["toy_demo"]),
            "also needs",
        ),
        (
            lambda doc: doc["workflows"][1]["tasks"].append("toy_opt"),
            "In two workflows",
        ),
        (
            lambda doc: doc["workflows"].pop(0),
            "In no workflow",
        ),
    ],
    ids=[
        "twice",
        "id",
        "task",
        "pipeline",
        "incomplete",
        "held-twice",
        "left-out",
    ],
)
def test_broken_workflows_are_rejected(break_it, message: str):
    """
    A workflow reusing an id, naming what is not there or holding a
    pipeline without its tasks stops the catalog from loading, and so
    does leaving anything outside every workflow.

    :param break_it: Mutates the fixture document.
    :type break_it: Callable[[dict], None]
    :param message: Text expected in the error.
    :type message: str
    """
    document = fixture_document()
    break_it(document)
    with pytest.raises(ValidationError, match=message):
        CatalogDocument.model_validate(document)


def test_a_catalog_from_before_workflows_still_loads():
    """
    Older releases have no workflows; their catalogs load with none.
    """
    document = fixture_document()
    del document["workflows"]
    assert not Catalog(CatalogDocument.model_validate(document)).workflows


def test_a_catalog_from_before_references_still_loads(catalog: Catalog):
    """
    Releases already published list no pages, and no task has any.

    :param catalog: The fixture catalog.
    :type catalog: Catalog
    """
    assert "references" not in fixture_document()
    assert catalog.pages_for(next(iter(catalog.tasks))) == []


def test_a_task_lists_the_pages_that_explain_it():
    """
    An https address and a guide in docs/ are both accepted.
    """
    document = fixture_document()
    task_id = document["tasks"][0]["id"]
    pages = [
        {"title": "Input", "page": "https://example.org/input.html"},
        {"title": "Guide", "page": "docs/quantum-espresso.md"},
    ]
    document["references"] = {task_id: pages}
    loaded = Catalog(CatalogDocument.model_validate(document))
    assert [page.title for page in loaded.pages_for(task_id)] == [
        "Input",
        "Guide",
    ]


@pytest.mark.parametrize(
    "page",
    [
        "http://example.org/not-encrypted.html",
        "file:///etc/passwd",
        "docs/../.env",
        "/etc/passwd",
        "https://example.org/has space",
    ],
)
def test_a_page_is_only_a_web_address_or_a_guide(page: str):
    """
    Nothing else can be listed, so the server never reads a local file
    outside docs/ or fetches an unencrypted address.

    :param page: A page that must be refused.
    :type page: str
    """
    document = fixture_document()
    task_id = document["tasks"][0]["id"]
    document["references"] = {task_id: [{"title": "Bad", "page": page}]}
    with pytest.raises(ValidationError):
        CatalogDocument.model_validate(document)


def test_pages_stay_out_of_what_agents_read():
    """
    Agents read a task strictly, so a new field in it would make one not
    yet copied again refuse every job. Pages live beside the tasks.
    """
    assert "references" not in TaskDefinition.model_fields


def test_pages_must_be_for_a_task_that_exists():
    """
    A misspelt task id fails when the catalog loads, not silently.
    """
    document = fixture_document()
    page = {"title": "Input", "page": "https://example.org/input.html"}
    document["references"] = {"no_such_task": [page]}
    with pytest.raises(ValidationError, match="no_such_task"):
        CatalogDocument.model_validate(document)


def test_a_limited_catalog_holds_only_what_its_workflows_hold(catalog: Catalog):
    """
    Limited to one workflow, the catalog lists only its tasks and
    pipelines and refuses the rest as unknown; the whole catalog is
    untouched.

    :param catalog: The fixture catalog.
    :type catalog: Catalog
    """
    limited = catalog.limited_to({"toy_other", "no_such_workflow"})
    assert list(limited.workflows) == ["toy_other"]
    assert list(limited.tasks) == ["toy_solo"]
    assert not limited.templates
    assert limited.validate_values("toy_solo", {}) == {}
    with pytest.raises(UnknownTaskError):
        limited.validate_values("toy_opt", {})
    assert set(catalog.tasks) == {"toy_opt", "toy_network", "toy_solo"}
    whole = catalog.limited_to({"toy_chain"})
    assert list(whole.templates) == ["toy_demo"]
    assert not catalog.limited_to(set()).tasks


def test_a_task_names_the_package_it_runs_from(catalog: Catalog):
    """
    Each task belongs to one workflow; a catalog from before workflows
    has none to name.

    :param catalog: The fixture catalog.
    :type catalog: Catalog
    """
    assert catalog.workflow_of("toy_opt") == "toy_chain"
    assert catalog.workflow_of("toy_solo") == "toy_other"
    document = fixture_document()
    del document["workflows"]
    older = Catalog(CatalogDocument.model_validate(document))
    assert older.workflow_of("toy_opt") is None


@pytest.mark.skipif(not REAL_CATALOG.exists(), reason="no scripts_repo")
def test_the_real_workflows_keep_the_pipelines_apart():
    """
    Someone given only Wannier90 gets its pipeline and tasks, and
    nothing of the nanoreactor.
    """
    limited = Catalog.from_path(REAL_CATALOG).limited_to({"wannier90"})
    assert list(limited.templates) == ["ahc"]
    assert "ahc_scf" in limited.tasks
    assert "xtb_opt" not in limited.tasks


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
        PYTHON, "-u", "-c", RUN_MAIN.format(module="toy.opt_driver"),
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


def test_an_input_takes_files_by_their_extension_in_any_case():
    """
    A file's type is its extension, in any case; a name without one
    (``xyz``) has no type, so no input takes it.
    """
    port = InputPort(name="structure", flag="-in", formats=["xyz"])
    assert port.takes("water.XYZ")
    assert not port.takes("xyz")
    assert not port.takes("water.pdb")


def waiting_parameter(document: dict[str, Any]) -> tuple[dict, dict]:
    """
    In a catalog document, make one parameter wait for a choice of
    another.

    :param document: The document, changed in place.
    :type document: dict[str, Any]
    :return: The one with choices, and the one waiting for it.
    :rtype: tuple[dict, dict]
    """
    parameters = document["tasks"][0]["parameters"]
    chooser = next(spec for spec in parameters if spec.get("choices"))
    waiting = next(spec for spec in parameters if spec is not chooser)
    waiting["show_when"] = {chooser["name"]: chooser["choices"][0]}
    return chooser, waiting


def test_a_form_field_can_wait_for_a_choice_of_another():
    """
    The form's fields load with the task.
    """
    document = fixture_document()
    _, waiting = waiting_parameter(document)
    waiting.update(group="Accuracy", advanced=True, widget="mesh", step=0.5)
    task = CatalogDocument.model_validate(document).tasks[0]
    loaded = {spec.name: spec for spec in task.parameters}[waiting["name"]]

    assert loaded.group == "Accuracy"
    assert loaded.widget == "mesh"
    assert loaded.show_when == waiting["show_when"]


def test_a_form_field_cannot_wait_for_a_value_never_offered():
    """
    A value outside the other parameter's choices would hide it for good.
    """
    document = fixture_document()
    chooser, waiting = waiting_parameter(document)
    waiting["show_when"] = {chooser["name"]: "never offered"}

    with pytest.raises(ValidationError, match="can't happen"):
        CatalogDocument.model_validate(document)
