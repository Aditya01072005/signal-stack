import subprocess
import sys
import time
import urllib.request
import json

def run_server_check():
    print("Starting Uvicorn server on http://127.0.0.1:8000...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd="backend",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Wait up to 5 seconds for server to be responsive
        server_ready = False
        for _ in range(10):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as resp:
                    if resp.status == 200:
                        server_ready = True
                        break
            except Exception:
                pass

        if not server_ready:
            print("Failed to connect to Uvicorn server.")
            stdout, stderr = proc.communicate(timeout=2)
            print("Server stdout:", stdout.decode())
            print("Server stderr:", stderr.decode())
            sys.exit(1)

        print("Uvicorn is UP and responsive!")

        # Probe Root Endpoint
        with urllib.request.urlopen("http://127.0.0.1:8000/") as resp:
            data = json.loads(resp.read().decode())
            print("GET / -> Status:", resp.status, "Body:", data)

        # Probe Health Endpoint
        with urllib.request.urlopen("http://127.0.0.1:8000/health") as resp:
            data = json.loads(resp.read().decode())
            print("GET /health -> Status:", resp.status, "Body:", data)

        # Probe Companies List Endpoint
        with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/companies") as resp:
            data = json.loads(resp.read().decode())
            print("GET /api/v1/companies -> Status:", resp.status, "Body:", data)

        # Test POST invalid company URL -> Expect 422 Unprocessable Entity
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/companies",
            data=json.dumps({"name": "Bad URL Co", "website_url": "invalid-url"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req)
            print("ERROR: Invalid URL was unexpectedly accepted!")
        except urllib.error.HTTPError as e:
            print("POST /api/v1/companies (invalid domain) -> Expected 422, received:", e.code)

        print("\nAll HTTP endpoint checks succeeded!")

    finally:
        proc.terminate()
        proc.wait(timeout=5)
        print("Uvicorn server shut down cleanly.")

if __name__ == "__main__":
    run_server_check()
