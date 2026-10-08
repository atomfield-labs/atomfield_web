"""
AtomField Sample Simulation Script
===================================
📚 LESSON: The Container Contract
    Every script that runs inside the AtomField Docker sandbox MUST:

    1. Accept parameters via environment variables or stdin (Phase 3 detail)
    2. Print its final result as a single JSON object to STDOUT
    3. Exit with code 0 on success, non-zero on failure

    This "contract" is what makes the system composable:
    the worker captures stdout, parses JSON, stores it as output_data (XCom),
    and the next node in the DAG reads it as its input parameters.

    This pattern is inspired by how Kubernetes sidecar containers communicate
    and how Apache Airflow's XCom system works.
"""

import json
import math
import sys


def run_band_structure_mock(parameters: dict) -> dict:
    """
    Mock a band structure calculation.
    In production this would call ASE, VASP, Quantum ESPRESSO, etc.
    """
    lattice_constant = parameters.get("lattice_constant_angstrom", 5.43)  # Silicon default
    temperature_k = parameters.get("temperature_k", 300)

    # Mock physics: simplified Kronig-Penney model approximation
    # (real DFT would take hours on a GPU cluster)
    band_gap = 1.12 * math.exp(-0.0005 * (temperature_k - 300))  # eV, temp-dependent
    total_energy = -8.94 * (5.43 / lattice_constant) ** 2  # eV/atom

    return {
        "result": "success",
        "metrics": {
            "band_gap_eV": round(band_gap, 4),
            "total_energy_eV_per_atom": round(total_energy, 4),
            "lattice_constant_angstrom": lattice_constant,
            "temperature_k": temperature_k,
            "fermi_energy_eV": round(-4.05 + 0.001 * temperature_k, 4),
        },
        "message": "Band structure calculation complete",
        "script": "sample_script.py",
    }


if __name__ == "__main__":
    # In Phase 3, parameters arrive via stdin as JSON from the worker
    try:
        raw = sys.stdin.read()
        params = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        params = {}

    result = run_band_structure_mock(params)

    # CRITICAL: Print ONLY valid JSON to stdout. No debug prints!
    # The worker reads stdout and parses it as the output_data.
    print(json.dumps(result))
