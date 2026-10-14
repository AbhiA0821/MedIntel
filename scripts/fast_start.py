import sys
import time
import subprocess
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

def main():
    print("[INIT] Starting MedIntel Fast Dev Environment...")

    # 1. Start FastAPI Backend on Port 8000
    print("  + Launching FastAPI Backend (Port 8000)...")
    backend_proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(PROJECT_ROOT)
    )

    # 2. Start Flask Frontend on Port 5000
    print("  + Launching Flask Frontend (Port 5000)...")
    frontend_proc = subprocess.Popen(
        [str(VENV_PYTHON), "frontend/app.py"],
        cwd=str(PROJECT_ROOT)
    )

    # 3. Quick Health Poll
    print("Waiting for health check (max 5s)...")
    healthy = False
    for _ in range(10):
        try:
            r = requests.get("http://127.0.0.1:8000/health", timeout=0.5)
            if r.status_code == 200:
                healthy = True
                break
        except Exception:
            pass
        time.sleep(0.5)

    if healthy:
        print("\n[SUCCESS] MedIntel is LIVE & READY!")
        print("   Frontend Dashboard: http://127.0.0.1:5000")
        print("   Backend API:        http://127.0.0.1:8000/docs")
    else:
        print("\n[INFO] Backend initial cold start in progress. Services ready at http://127.0.0.1:5000")

if __name__ == "__main__":
    main()
