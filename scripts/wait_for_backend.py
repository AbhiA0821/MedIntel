"""
MedIntel Backend Readiness Checker
Waits for the FastAPI backend (/health) to become fully available and responsive.
"""

import sys
import time
import urllib.request
import urllib.error

def wait_for_backend(url="http://127.0.0.1:8000/health", max_retries=35, delay=1.0):
    start_time = time.time()
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MedIntel-HealthCheck/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    elapsed = time.time() - start_time
                    print(f"Backend became ready in {elapsed:.1f}s (attempt {attempt}/{max_retries}).")
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            pass
        except Exception:
            pass
        time.sleep(delay)
    return False

if __name__ == "__main__":
    is_ready = wait_for_backend()
    sys.exit(0 if is_ready else 1)
