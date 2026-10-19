import requests
import time
import json

payload = {
  "nodes": [
    {"ui_id": "node_A", "script_name": "simulate.py", "parameters": {"iterations": 100, "node": "A"}},
    {"ui_id": "node_B", "script_name": "simulate.py", "parameters": {"iterations": 200, "node": "B"}},
    {"ui_id": "node_C", "script_name": "simulate.py", "parameters": {"iterations": 300, "node": "C"}}
  ],
  "edges": [
    {"upstream_ui_id": "node_A", "downstream_ui_id": "node_C"},
    {"upstream_ui_id": "node_B", "downstream_ui_id": "node_C"}
  ]
}

print("Submitting Pipeline...")
res = requests.post("http://localhost:8000/api/jobs/pipeline/submit", json=payload)
print(res.status_code)
print(json.dumps(res.json(), indent=2))

print("\nWaiting for 25 seconds for nodes to process...")
time.sleep(25)

print("\nFetching all jobs:")
res_list = requests.get("http://localhost:8000/api/jobs?limit=10")
print(json.dumps(res_list.json(), indent=2))
