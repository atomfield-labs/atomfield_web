"""
The pipeline templates the UI offers must pass submission validation.
"""

from pathlib import Path

import pytest

from app.api.routes.mock import (
    AHC_BLUEPRINT,
    MODULAR_NANOREACTOR_BLUEPRINT,
    NANOREACTOR_BLUEPRINT,
)
from app.catalog.catalog import Catalog
from app.services.submission_validation import check_task_request

REAL_CATALOG = Path(__file__).resolve().parents[1] / "scripts_repo"
REAL_CATALOG = REAL_CATALOG / "catalog.json"


@pytest.mark.skipif(not REAL_CATALOG.exists(), reason="no scripts_repo")
@pytest.mark.parametrize(
    "blueprint",
    [NANOREACTOR_BLUEPRINT, MODULAR_NANOREACTOR_BLUEPRINT, AHC_BLUEPRINT],
    ids=["flash", "modular", "ahc"],
)
def test_template_nodes_are_valid_submissions(blueprint: dict):
    """
    Every task node of a template names a real task, with valid
    parameters and input ports.

    :param blueprint: Template served by the mock routes.
    :type blueprint: dict
    """
    catalog = Catalog.from_path(REAL_CATALOG)
    task_nodes = [n for n in blueprint["nodes"] if "script_name" in n]
    for index, node in enumerate(task_nodes):
        check_task_request(
            catalog,
            node["script_name"],
            node["parameters"],
            node.get("inputs", {}),
            ("template", index),
        )


def test_the_ahc_template_chains_its_four_steps_in_order():
    """
    Structure -> SCF -> NSCF -> Wannier -> Berry: each step reads the
    one before it, so the chain must not skip or reorder a step.
    """
    links = [
        (edge["upstream_ui_id"], edge["downstream_ui_id"])
        for edge in AHC_BLUEPRINT["edges"]
    ]
    steps = ["structure_fe", "ahc_scf", "ahc_nscf", "ahc_wannier"]

    assert links == list(zip(steps, [*steps[1:], "ahc_berry"]))
