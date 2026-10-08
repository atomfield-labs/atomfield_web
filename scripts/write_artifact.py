import json
import os

def main():
    workspace = "/workspace"
    output_file = os.path.join(workspace, "output.txt")
    
    with open(output_file, "w") as f:
        f.write("Hello from Script A!")
    
    result = {"status": "success", "message": "Wrote output to workspace"}
    print(json.dumps(result))

if __name__ == "__main__":
    main()
