import time, urllib.request

for endpoint in ["http://localhost:8000/health", "http://localhost:3000/login"]:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.5)
    else:
        raise SystemExit("Service unavailable: " + endpoint)
print("API and web are ready")
