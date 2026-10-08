import json
import os

def main():
    workspace = "/workspace"
    output_file = os.path.join(workspace, "output.txt")
    
    try:
        with open(output_file, "r") as f:
            content = f.read()
        result = {"status": "success", "read_content": content}
    except Exception as e:
        result = {"status": "failed", "error": str(e)}
        
    print(json.dumps(result))

if __name__ == "__main__":
    main()
