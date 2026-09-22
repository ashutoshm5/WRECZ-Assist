"""Start the WRECZ bridge and the frontend together.

Backend  http://127.0.0.1:8765  (api_server.py)
Frontend http://127.0.0.1:8443  (Vite dev server)

The frontend's origin is the one allowed by the bridge's CORS policy, so both
ports have to match what api_server.py permits.
"""

import os
import shutil
import subprocess
import sys
import time

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = "8765"
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = "8443"


def run():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.abspath(
        os.path.join(root_dir, "..", "wrecz-frontend")
    )

    if not os.path.isdir(frontend_dir):
        print(f"[ORCHESTRATOR] Frontend not found at {frontend_dir}")
        return 1

    npm_cmd = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")

    if npm_cmd is None:
        print("[ORCHESTRATOR] npm is not on PATH. Install Node.js first.")
        return 1

    if not os.path.isdir(os.path.join(frontend_dir, "node_modules")):
        print("[ORCHESTRATOR] Installing frontend dependencies...")
        subprocess.run([npm_cmd, "install"], cwd=frontend_dir, check=True)

    print(
        f"[ORCHESTRATOR] Starting WRECZ API Server on "
        f"{BACKEND_HOST}:{BACKEND_PORT}..."
    )

    backend_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api_server:app",
            "--host",
            BACKEND_HOST,
            "--port",
            BACKEND_PORT,
            "--log-level",
            "info",
        ],
        cwd=root_dir,
    )

    time.sleep(1.5)

    if backend_proc.poll() is not None:
        print("[ORCHESTRATOR] WRECZ API Server exited during startup.")
        return backend_proc.returncode

    print(
        f"[ORCHESTRATOR] Starting Vite Frontend on "
        f"{FRONTEND_HOST}:{FRONTEND_PORT}..."
    )

    frontend_proc = subprocess.Popen(
        [
            npm_cmd,
            "run",
            "dev",
            "--",
            "--port",
            FRONTEND_PORT,
            "--host",
            FRONTEND_HOST,
        ],
        cwd=frontend_dir,
    )

    print(
        f"[ORCHESTRATOR] WRECZ is at "
        f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"
    )

    processes = {
        "API server": backend_proc,
        "frontend": frontend_proc,
    }

    try:
        # Either half going down makes WRECZ unusable, so the first exit
        # tears the other one down instead of leaving an orphan behind.
        while True:
            for name, process in processes.items():
                if process.poll() is not None:
                    print(
                        f"[ORCHESTRATOR] The {name} exited "
                        f"(code {process.returncode}). Shutting down."
                    )
                    return process.returncode or 0

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[ORCHESTRATOR] Shutting down WRECZ instances...")
        return 0

    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()

        for process in processes.values():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(run())
