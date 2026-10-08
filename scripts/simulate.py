import os
import json
import time

def main():
    # Read parameters passed by the execution engine via env var
    params_str = os.getenv("JOB_PARAMS", "{}")
    
    try:
        params = json.loads(params_str)
    except json.JSONDecodeError:
        params = {}
    
    # Simulate heavy computation
    time.sleep(2)
    
    # Generate output artifact
    result = {
        "status": "simulation_complete",
        "iterations_run": params.get("iterations", 100),
        "final_energy": -42.875
    }
    
    # Print JSON (This is captured by the Docker SDK stdout)
    print(json.dumps(result))

if __name__ == "__main__":
    main()
