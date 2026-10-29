"""
Simulation blueprints and mock authentication quota handlers.
"""

import json

from fastapi import APIRouter

router = APIRouter(tags=["Simulation Blueprints"])

DEFAULT_NANOREACTOR_NETWORK = {
    "directed": True,
    "multigraph": False,
    "graph": {
        "name": "Ethanol Pyrolysis Discovery Network",
        "method": "GFN2-xTB / SevenNet-0",
    },
    "nodes": [
        {
            "id": "CCO",
            "name": "Ethanol",
            "smiles": "CCO",
            "formula": "C2H6O",
            "node_type": "Reactant",
            "energy_ev": -154.215,
            "conformers": 12,
        },
        {
            "id": "C=C",
            "name": "Ethylene",
            "smiles": "C=C",
            "formula": "C2H4",
            "node_type": "Product",
            "energy_ev": -78.102,
            "conformers": 8,
        },
        {
            "id": "O",
            "name": "Water",
            "smiles": "O",
            "formula": "H2O",
            "node_type": "Product",
            "energy_ev": -76.054,
            "conformers": 14,
        },
        {
            "id": "CC=O",
            "name": "Acetaldehyde",
            "smiles": "CC=O",
            "formula": "C2H4O",
            "node_type": "Intermediate",
            "energy_ev": -152.882,
            "conformers": 6,
        },
        {
            "id": "[H][H]",
            "name": "Hydrogen Gas",
            "smiles": "[H][H]",
            "formula": "H2",
            "node_type": "Product",
            "energy_ev": -6.741,
            "conformers": 9,
        },
        {
            "id": "[C-]#[O+]",
            "name": "Carbon Monoxide",
            "smiles": "[C-]#[O+]",
            "formula": "CO",
            "node_type": "Product",
            "energy_ev": -113.805,
            "conformers": 4,
        },
        {
            "id": "C",
            "name": "Methane",
            "smiles": "C",
            "formula": "CH4",
            "node_type": "Product",
            "energy_ev": -40.501,
            "conformers": 5,
        },
    ],
    "links": [
        {
            "source": "CCO",
            "target": "C=C",
            "reaction": "Dehydration: C2H6O -> C2H4 + H2O",
            "Ea": 1.85,
            "delta_E": 0.059,
        },
        {
            "source": "CCO",
            "target": "O",
            "reaction": "Dehydration Coproduct",
            "Ea": 1.85,
            "delta_E": 0.059,
        },
        {
            "source": "CCO",
            "target": "CC=O",
            "reaction": "Dehydrogenation: C2H6O -> C2H4O + H2",
            "Ea": 2.15,
            "delta_E": 1.333,
        },
        {
            "source": "CCO",
            "target": "[H][H]",
            "reaction": "Dehydrogenation Coproduct",
            "Ea": 2.15,
            "delta_E": 1.333,
        },
        {
            "source": "CC=O",
            "target": "C",
            "reaction": "Decarbonylation: C2H4O -> CH4 + CO",
            "Ea": 2.90,
            "delta_E": -1.424,
        },
        {
            "source": "CC=O",
            "target": "[C-]#[O+]",
            "reaction": "Decarbonylation Coproduct",
            "Ea": 2.90,
            "delta_E": -1.424,
        },
    ],
}

DEFAULT_NANOREACTOR_NETWORK_JSON = json.dumps(
    DEFAULT_NANOREACTOR_NETWORK, indent=2
)

DEFAULT_NANOREACTOR_SUMMARY_TXT = (
    "====================================================\n"
    "  AtomField Nanoreactor Reaction Discovery Summary\n"
    "====================================================\n"
    "Execution Engine: AtomField v1.0.0 (xTB / SevenNet-0)\n"
    "Reactant: Ethanol (C2H6O)\n"
    "Temperature: 1200 K\n"
    "Trajectory Replicates: 5 (10.0 ps total sampling)\n\n"
    "Discovered Unique Species (Nodes): 7\n"
    "Discovered Reaction Pathways (Edges): 6\n\n"
    "Species List:\n"
    "  [1] CCO      | Ethanol          | Reactant     | 12 conformers"
    " | -154.215 eV\n"
    "  [2] C=C      | Ethylene         | Product      |  8 conformers"
    " |  -78.102 eV\n"
    "  [3] O        | Water            | Product      | 14 conformers"
    " |  -76.054 eV\n"
    "  [4] CC=O     | Acetaldehyde     | Intermediate |  6 conformers"
    " | -152.882 eV\n"
    "  [5] [H][H]   | Hydrogen Gas     | Product      |  9 conformers"
    " |   -6.741 eV\n"
    "  [6] [C-]#[O+]| Carbon Monoxide  | Product      |  4 conformers"
    " | -113.805 eV\n"
    "  [7] C        | Methane          | Product      |  5 conformers"
    " |  -40.501 eV\n\n"
    "Key Reaction Barriers:\n"
    "  - Pathway 1: CCO -> C=C + H2O     | Ea = 1.85 eV (42.7 kcal/mol)\n"
    "  - Pathway 2: CCO -> CC=O + H2     | Ea = 2.15 eV (49.6 kcal/mol)\n"
    "  - Pathway 3: CC=O -> CH4 + CO     | Ea = 2.90 eV (66.9 kcal/mol)\n"
)

DEFAULT_NANOREACTOR_LOG = (
    "[INFO] Starting xTB Nanoreactor simulation...\n"
    "[INFO] Loaded input structure: ethanol.xyz (9 atoms, formula C2H6O)\n"
    "[INFO] Initial GFN2-xTB optimization converged (Energy: -154.215 eV)\n"
    "[INFO] Spawning 5 parallel Born-Oppenheimer MD replicates at T=1200K...\n"
    "[INFO] Replicate 1 completed: 2000 steps, 14 bond reorganization events.\n"
    "[INFO] Replicate 2 completed: 2000 steps, 18 bond reorganization events.\n"
    "[INFO] Extracting distinct chemical topologies with RDKit perception...\n"
    "[INFO] Discovered 7 unique molecular species across all trajectories.\n"
    "[INFO] Relaxing conformers using SevenNet-0 neural network potential...\n"
    "[INFO] Locating transition states via Sella eigenvector-following...\n"
    "[INFO] TS search converged for dehydration barrier (Ea = 1.85 eV).\n"
    "[INFO] Nanoreactor discovery completed. Output: reaction_network.json.\n"
)


ETHANOL_RAW_XYZ = (
    "9\n"
    "Ethanol molecule\n"
    "C       -0.0387    0.0468    0.0000\n"
    "C        1.4613    0.0468    0.0000\n"
    "O        1.9613    1.3668    0.0000\n"
    "H       -0.4023   -0.4682    0.8900\n"
    "H       -0.4023   -0.4682   -0.8900\n"
    "H       -0.4023    1.0768    0.0000\n"
    "H        1.8249   -0.4682   -0.8900\n"
    "H        1.8249   -0.4682    0.8900\n"
    "H        2.9213    1.3668    0.0000\n"
)

NANOREACTOR_PARAMETERS = {
    "nreplicates": 5,
    "workers": 2,
    "temp": 1000.0,
    "time": 20.0,
    "step": 1.0,
    "refine": "sevennet",
    "ts_search": "sella_neb",
    "ts_engine": "sevennet",
    "neb_engine": "sevennet",
    "nimages": 10,
    "rxn_filter": "smiles",
}

NANOREACTOR_BLUEPRINT = {
    "nodes": [
        {
            "ui_id": "structure_ethanol",
            "id": "structure_ethanol",
            "type": "structure",
            "filename": "ethanol.xyz",
            "workspace_path": "/workspace/ethanol.xyz",
            "format": "XYZ",
            "formula": "C2H6O",
            "atom_count": 9,
            "raw_content": ETHANOL_RAW_XYZ,
            "position": {"x": 100, "y": 220},
        },
        {
            "ui_id": "xtb_nanoreactor",
            "id": "xtb_nanoreactor",
            "script_name": "xtb_nanoreactor",
            "label": "Nanoreactor Flash",
            "status": "Ready",
            "parameters": NANOREACTOR_PARAMETERS,
            "inputs": {"structure": ["ethanol.xyz"]},
            "default_parameters": NANOREACTOR_PARAMETERS,
            "position": {"x": 380, "y": 220},
        },
    ],
    "edges": [
        {
            "id": "e-structure_ethanol-xtb_nanoreactor",
            "upstream_ui_id": "structure_ethanol",
            "downstream_ui_id": "xtb_nanoreactor",
            "source_handle": "structure-out",
            "target_handle": "target-left",
        }
    ],
}


MODULAR_NANOREACTOR_BLUEPRINT = {
    "nodes": [
        {
            "ui_id": "structure_ethanol",
            "id": "structure_ethanol",
            "type": "structure",
            "filename": "ethanol.xyz",
            "workspace_path": "/workspace/ethanol.xyz",
            "format": "XYZ",
            "formula": "C2H6O",
            "atom_count": 9,
            "raw_content": ETHANOL_RAW_XYZ,
            "position": {"x": 100, "y": 140},
        },
        {
            "ui_id": "xtb_opt_1",
            "id": "xtb_opt_1",
            "script_name": "xtb_opt",
            "label": "xTB Geometry Optimization",
            "inputs": {"structure": ["ethanol.xyz"]},
            "status": "Ready",
            "parameters": {
                "gfn": 2,
                "charge": 0,
                "optlevel": "normal",
                "maxcycle": 250,
            },
            "default_parameters": {
                "gfn": 2,
                "charge": 0,
                "optlevel": "normal",
                "maxcycle": 250,
            },
            "position": {"x": 360, "y": 140},
        },
        {
            "ui_id": "xtb_md_1",
            "id": "xtb_md_1",
            "script_name": "xtb_md",
            "label": "xTB Molecular Dynamics",
            "status": "Ready",
            "parameters": {
                "gfn": 2,
                "charge": 0,
                "temp": 1200.0,
                "time": 10.0,
                "step": 1.0,
            },
            "default_parameters": {
                "gfn": 2,
                "charge": 0,
                "temp": 1200.0,
                "time": 10.0,
                "step": 1.0,
            },
            "position": {"x": 620, "y": 140},
        },
        {
            "ui_id": "rxn_network_1",
            "id": "rxn_network_1",
            "script_name": "rxn_network",
            "label": "Reaction Network Mapper",
            "status": "Ready",
            "parameters": {
                "charge": 0,
                "rxn_filter": "smiles",
            },
            "default_parameters": {
                "charge": 0,
                "rxn_filter": "smiles",
            },
            "position": {"x": 620, "y": 320},
        },
        {
            "ui_id": "mlff_refine_1",
            "id": "mlff_refine_1",
            "script_name": "mlff_refine",
            "label": "SevenNet Conformer Refinement",
            "status": "Ready",
            "parameters": {
                "engine": "sevennet",
                "model": "7net-0",
                "fmax": 0.01,
                "steps": 250,
                "charge": 0,
            },
            "default_parameters": {
                "engine": "sevennet",
                "model": "7net-0",
                "fmax": 0.01,
                "steps": 250,
                "charge": 0,
            },
            "position": {"x": 880, "y": 320},
        },
        {
            "ui_id": "ts_search_1",
            "id": "ts_search_1",
            "script_name": "ts_search",
            "label": "Transition State Search",
            "status": "Ready",
            "parameters": {
                "ts_search": "sella_neb",
                "neb_engine": "sevennet",
                "ts_engine": "sevennet",
                "nimages": 10,
                "charge": 0,
            },
            "default_parameters": {
                "ts_search": "sella_neb",
                "neb_engine": "sevennet",
                "ts_engine": "sevennet",
                "nimages": 10,
                "charge": 0,
            },
            "position": {"x": 1140, "y": 320},
        },
    ],
    "edges": [
        {
            "id": "e-structure-opt",
            "upstream_ui_id": "structure_ethanol",
            "downstream_ui_id": "xtb_opt_1",
            "source_handle": "structure-out",
            "target_handle": "target-left",
        },
        {
            "id": "e-opt-md",
            "upstream_ui_id": "xtb_opt_1",
            "downstream_ui_id": "xtb_md_1",
            "source_handle": "source-right",
            "target_handle": "target-left",
        },
        {
            "id": "e-md-rxn",
            "upstream_ui_id": "xtb_md_1",
            "downstream_ui_id": "rxn_network_1",
            "source_handle": "source-bottom",
            "target_handle": "target-top",
        },
        {
            "id": "e-rxn-refine",
            "upstream_ui_id": "rxn_network_1",
            "downstream_ui_id": "mlff_refine_1",
            "source_handle": "source-right",
            "target_handle": "target-left",
        },
        {
            "id": "e-refine-ts",
            "upstream_ui_id": "mlff_refine_1",
            "downstream_ui_id": "ts_search_1",
            "source_handle": "source-right",
            "target_handle": "target-left",
        },
    ],
}


# Primitive bcc Fe (a = 2.8665 Å) as a minimal pw.x input, which the
# SCF reads as a structure. Unlike a CIF it keeps the cell's
# orientation: the cube's axes along x, y and z, so the magnetization
# (along z) points along [001] and sigma_xy is the Hall conductivity
# usually reported.
FE_BCC_PRIMITIVE_IN = (
    "&CONTROL\n"
    "/\n"
    "&SYSTEM\n"
    "  ibrav = 0, nat = 1, ntyp = 1,\n"
    "/\n"
    "&ELECTRONS\n"
    "/\n"
    "ATOMIC_SPECIES\n"
    "  Fe 55.845 Fe.UPF\n"
    "CELL_PARAMETERS angstrom\n"
    "   1.43325   1.43325   1.43325\n"
    "  -1.43325   1.43325   1.43325\n"
    "  -1.43325  -1.43325   1.43325\n"
    "ATOMIC_POSITIONS crystal\n"
    "  Fe 0.0 0.0 0.0\n"
    "K_POINTS gamma\n"
)
FE_BCC_FILENAME = "fe_bcc_primitive.in"
TEMPLATE_ROW_Y = 220


def template_task_node(
    task_id: str,
    label: str,
    x: int,
    parameters: dict | None = None,
    inputs: dict | None = None,
) -> dict:
    """
    One task node of a pipeline template, in a row, keyed by its task
    (so its job's folder is named after it). Parameters name only what
    differs from the task's defaults; the editor fills in the rest
    from the catalog.

    :param task_id: Catalog task.
    :type task_id: str
    :param label: Name shown on the node.
    :type label: str
    :param x: Horizontal position on the canvas.
    :type x: int
    :param parameters: Values that differ from the defaults.
    :type parameters: dict | None
    :param inputs: Input port -> uploaded files.
    :type inputs: dict | None
    :return: The node.
    :rtype: dict
    """
    values = parameters or {}
    return {
        "ui_id": task_id,
        "id": task_id,
        "script_name": task_id,
        "label": label,
        "status": "Ready",
        "parameters": values,
        "default_parameters": values,
        "inputs": inputs or {},
        "position": {"x": x, "y": TEMPLATE_ROW_Y},
    }


def template_edge(upstream: str, downstream: str) -> dict:
    """
    A link from one template node's right side to the next one's left.

    :param upstream: Node the data comes from.
    :type upstream: str
    :param downstream: Node it goes to.
    :type downstream: str
    :return: The edge.
    :rtype: dict
    """
    is_structure = upstream.startswith("structure")
    return {
        "id": f"e-{upstream}-{downstream}",
        "upstream_ui_id": upstream,
        "downstream_ui_id": downstream,
        "source_handle": "structure-out" if is_structure else "source-right",
        "target_handle": "target-left",
    }


# Anomalous Hall conductivity in four Quantum ESPRESSO and Wannier90
# steps, set up for bcc Fe magnetized along z.
AHC_BLUEPRINT = {
    "nodes": [
        {
            "ui_id": "structure_fe",
            "id": "structure_fe",
            "type": "structure",
            "filename": FE_BCC_FILENAME,
            "workspace_path": f"/workspace/{FE_BCC_FILENAME}",
            "format": "IN",
            "formula": "Fe",
            "atom_count": 1,
            "raw_content": FE_BCC_PRIMITIVE_IN,
            "position": {"x": 80, "y": TEMPLATE_ROW_Y},
        },
        template_task_node(
            "ahc_scf",
            "SCF with spin-orbit",
            340,
            {"magnetization": "Fe=0.5", "kmesh": "10 10 10"},
            {"structure": [FE_BCC_FILENAME]},
        ),
        template_task_node("ahc_nscf", "NSCF on the full mesh", 600),
        template_task_node("ahc_wannier", "Wannier90", 860),
        template_task_node("ahc_berry", "Berry curvature & AHC", 1120),
    ],
    "edges": [
        template_edge("structure_fe", "ahc_scf"),
        template_edge("ahc_scf", "ahc_nscf"),
        template_edge("ahc_nscf", "ahc_wannier"),
        template_edge("ahc_wannier", "ahc_berry"),
    ],
}


@router.get("/pipeline/nanoreactor/blueprint")
async def get_blueprint() -> dict:
    """
    Retrieve prebuilt topology blueprint for the monolithic xTB nanoreactor run.

    :return: Dictionary containing preconfigured nodes and edges.
    :rtype: dict
    """
    return NANOREACTOR_BLUEPRINT


@router.get("/pipeline/nanoreactor_modular/blueprint")
async def get_modular_blueprint() -> dict:
    """
    Retrieve decomposed 5-node pipeline blueprint for modular reaction
    discovery.

    :return: Dictionary containing preconfigured nodes and edges for 5
        lean nodes.
    :rtype: dict
    """
    return MODULAR_NANOREACTOR_BLUEPRINT


@router.get("/pipeline/ahc/blueprint")
async def get_ahc_blueprint() -> dict:
    """
    Retrieve the four-step anomalous Hall conductivity pipeline (SCF,
    NSCF, Wannier90, Berry curvature), set up for bcc Fe.

    :return: Dictionary containing preconfigured nodes and edges.
    :rtype: dict
    """
    return AHC_BLUEPRINT


@router.get("/auth/quota")
async def get_quota() -> dict:
    """
    Retrieve current remaining compute execution quota.

    :return: Dictionary containing runsRemaining count.
    :rtype: dict
    """
    return {"runsRemaining": 9999}
