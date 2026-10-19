"""
Simulation blueprints and mock authentication quota handlers.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Simulation Blueprints"])

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
