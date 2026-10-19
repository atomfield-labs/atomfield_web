"""
Sample simulation script demonstrating worker execution contract.
Accepts parameters via stdin and returns a JSON payload to stdout.
"""

import json
import math
import sys


def run_band_structure_mock(parameters: dict) -> dict:
    """
    Simulates a band structure calculation.
    """
    lattice_constant = parameters.get("lattice_constant_angstrom", 5.43)
    temperature_k = parameters.get("temperature_k", 300)

    band_gap = 1.12 * math.exp(-0.0005 * (temperature_k - 300))
    total_energy = -8.94 * (5.43 / lattice_constant) ** 2

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
    try:
        raw = sys.stdin.read()
        params = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        params = {}

    result = run_band_structure_mock(params)
    print(json.dumps(result))
