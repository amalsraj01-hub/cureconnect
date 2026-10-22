"""Smoke-test the app the way Render will actually run it.

Render starts the service with:
    uvicorn app.main:app --host 0.0.0.0 --port $PORT
from the repository root of a clean checkout, and probes /health to decide
whether the instance is up. This script starts the same command, from the
same working directory, and then asks the server the questions a user (or a
Render health check) would ask:

  * does the process start at all?
  * does /health answer (this is the health-check path in render.yaml)?
  * does /docs answer (FastAPI's own UI)?
  * does / answer with the frontend page (the app mounts it at "/")?
  * does /recommend work end to end against the real Overpass API?

Anything that fails here would fail in production too, so it is worth
running before clicking "Deploy".
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("SMOKE_PORT", "8123"))
BASE = f"http://127.0.0.1:{PORT}"
LOG = ROOT / "_smoke_server.log"

# Wait this long for /health. A cold start on a free instance can take ~30 s,
# locally it is fast, but the timeout is generous on purpose.
STARTUP_TIMEOUT_S = 90


def http(path, data=None, timeout=60):
    """GET or POST JSON. Returns (status, body_text)."""
    url = BASE + path
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def check(label, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + label + (("  -> " + detail) if detail else ""))
    sys.stdout.flush()
    return ok


def main():
    results = []

    cmd = [sys.executable, "-m", "uvicorn", "app.main:app",
           "--host", "0.0.0.0", "--port", str(PORT)]
    print("starting:", " ".join(cmd))
    log = open(LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)
    try:
        # 1. /health - the same path render.yaml tells Render to probe.
        deadline = time.time() + STARTUP_TIMEOUT_S
        status = None
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            status, body = http("/health", timeout=5)
            if status == 200:
                break
            time.sleep(1)
        if proc.poll() is not None:
            print("server exited with code", proc.returncode)
            print(LOG.read_text(encoding="utf-8", errors="replace")[-3000:])
            return 1
        results.append(check("GET /health returns 200", status == 200, str(status)))

        # 2. /docs - FastAPI's interactive API page.
        status, body = http("/docs")
        results.append(check("GET /docs returns 200", status == 200, str(status)))

        # 3. / - the frontend, mounted by app/main.py.
        status, body = http("/")
        ok = status == 200 and "CureConnect" in body
        results.append(check("GET / serves the frontend page", ok, str(status)))

        # 4. The frontend must call the API on its own origin. If this were an
        #    absolute localhost URL the page would work locally and break in
        #    production, so it is asserted here rather than eyeballed.
        ok = 'const API = ""' in body
        results.append(check("frontend uses a same-origin API URL", ok))

        # 5. An emergency must short-circuit before any network call.
        status, body = http("/recommend", {
            "symptoms": "severe chest pain and difficulty breathing",
            "lat": 11.8745, "lng": 75.3704})
        ok = status == 200 and json.loads(body).get("emergency") is True
        results.append(check("POST /recommend detects an emergency", ok, str(status)))

        # 6. The real thing: classifier + live Overpass call for Kannur.
        status, body = http("/recommend", {
            "symptoms": "I have had a headache and fever for three days",
            "lat": 11.8745, "lng": 75.3704}, timeout=90)
        ok = status == 200
        if ok:
            payload = json.loads(body)
            ok = payload.get("emergency") is False and "doctors" in payload
            detail = f"status={status} condition={payload.get('prediction', {}).get('condition')} " \
                     f"doctors={len(payload.get('doctors', []))}"
        else:
            detail = f"status={status} body={body[:300]}"
        results.append(check("POST /recommend works end to end (Kannur)", ok, detail))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    passed = sum(1 for r in results if r)
    print("-" * 60)
    print(f"{passed}/{len(results)} smoke checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
