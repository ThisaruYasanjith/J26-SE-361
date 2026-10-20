"""
Microservice entrypoint inside models directory.
Delegates to Exceptions/serve.py.
"""
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from serve import run_server

if __name__ == "__main__":
    run_server()
