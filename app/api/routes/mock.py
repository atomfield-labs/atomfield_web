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
    "jobname": "nanoreactor",
    "input": "/workspace/ethanol.xyz",
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
            "script_name": "xtb_nanoreactor.py",
            "label": "Nanoreactor Flash",
            "status": "Ready",
            "parameters": NANOREACTOR_PARAMETERS,
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
            "script_name": "xtbopt_driver.py",
            "label": "xTB Geometry Optimization",
            "status": "Ready",
            "parameters": {
                "gfn": 2,
                "charge": 0,
                "optlevel": "normal",
                "maxcycle": 250,
                "jobname": "xtb_opt",
            },
            "default_parameters": {
                "gfn": 2,
                "charge": 0,
                "optlevel": "normal",
                "maxcycle": 250,
                "jobname": "xtb_opt",
            },
            "position": {"x": 360, "y": 140},
        },
        {
            "ui_id": "xtb_md_1",
            "id": "xtb_md_1",
            "script_name": "xtbmd_driver.py",
            "label": "xTB Molecular Dynamics",
            "status": "Ready",
            "parameters": {
                "gfn": 2,
                "charge": 0,
                "temp": 1200.0,
                "time": 10.0,
                "step": 1.0,
                "jobname": "xtb_md",
            },
            "default_parameters": {
                "gfn": 2,
                "charge": 0,
                "temp": 1200.0,
                "time": 10.0,
                "step": 1.0,
                "jobname": "xtb_md",
            },
            "position": {"x": 620, "y": 140},
        },
        {
            "ui_id": "rxn_network_1",
            "id": "rxn_network_1",
            "script_name": "rxn_network_driver.py",
            "label": "Reaction Network Mapper",
            "status": "Ready",
            "parameters": {
                "charge": 0,
                "rxn_filter": "smiles",
                "jobname": "rxn_network",
            },
            "default_parameters": {
                "charge": 0,
                "rxn_filter": "smiles",
                "jobname": "rxn_network",
            },
            "position": {"x": 620, "y": 320},
        },
        {
            "ui_id": "mlff_refine_1",
            "id": "mlff_refine_1",
            "script_name": "mlff_refine_driver.py",
            "label": "SevenNet Conformer Refinement",
            "status": "Ready",
            "parameters": {
                "engine": "sevennet",
                "model": "7net-0",
                "fmax": 0.01,
                "steps": 250,
                "charge": 0,
                "jobname": "mlff_refine",
            },
            "default_parameters": {
                "engine": "sevennet",
                "model": "7net-0",
                "fmax": 0.01,
                "steps": 250,
                "charge": 0,
                "jobname": "mlff_refine",
            },
            "position": {"x": 880, "y": 320},
        },
        {
            "ui_id": "ts_search_1",
            "id": "ts_search_1",
            "script_name": "ts_search_driver.py",
            "label": "Transition State Search",
            "status": "Ready",
            "parameters": {
                "ts_search": "sella_neb",
                "neb_engine": "sevennet",
                "ts_engine": "sevennet",
                "nimages": 10,
                "charge": 0,
                "jobname": "ts_search",
            },
            "default_parameters": {
                "ts_search": "sella_neb",
                "neb_engine": "sevennet",
                "ts_engine": "sevennet",
                "nimages": 10,
                "charge": 0,
                "jobname": "ts_search",
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
    Retrieve decomposed 5-node pipeline blueprint for modular reaction discovery.

    :return: Dictionary containing preconfigured nodes and edges for 5 lean nodes.
    :rtype: dict
    """
    return MODULAR_NANOREACTOR_BLUEPRINT



@router.get("/auth/quota")
async def get_quota() -> dict:
    """
    Retrieve current remaining compute execution quota.

    :return: Dictionary containing runsRemaining count.
    :rtype: dict
    """
    return {"runsRemaining": 9999}
