import uvicorn
import os
import sys
import socket

# Ensure root and backend are in the path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
backend_dir = os.path.join(root_dir, 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

def find_available_port(default_port=8000, fallback_ports=(8080, 8008, 5000, 8888)):
    for port in [default_port, *fallback_ports]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return default_port

if __name__ == "__main__":
    env_port = os.getenv("PORT")
    port = int(env_port) if env_port else find_available_port(8000)

    print("=========================================================")
    print(" GrowthPilot AI - Starting FastAPI Server...")
    print(f" Web Interface URL: http://127.0.0.1:{port}")
    print(f" A2A Protocol Manifest: http://127.0.0.1:{port}/.well-known/agent.json")
    print("=========================================================")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, reload=True)

