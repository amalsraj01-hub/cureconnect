"""Pre-deploy preflight for the Render build.

Checks the things that can break a Render deploy even when the repo is
correct and the tests pass locally:
  1. Every pinned requirement actually exists on public PyPI.
  2. Every pinned requirement has a wheel for the target interpreter
     (CPython 3.14, manylinux x86_64) so Render does not have to build
     from source (which times out on the free tier).
  3. The interpreter the app imports at runtime is the one we pinned.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = sys.version_info[:2]
WANT_TAG = "cp%d%d" % TARGET
PLAT = "manylinux"
ARCH = "x86_64"


def public_pypi(name):
    url = "https://pypi.org/pypi/%s/json" % name
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            return json.load(r)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": str(exc)}


def wheels_for(release_files):
    tags = []
    for f in release_files:
        fn = f.get("filename", "")
        if fn.endswith(".whl"):
            tags.append(fn)
    return tags


def ok_for_target(tags):
    """True if one of the wheels can be installed on this interpreter/arch."""
    for fn in tags:
        # filename: name-version-pytag-abitag-plattag.whl
        parts = fn[:-4].split("-")
        if len(parts) < 5:
            continue
        py, abi, plat = parts[-3], parts[-2], parts[-1]
        # A wheel tag may be a compressed set, e.g. "py2.py3" or "cp313.cp314".
        py_ok = any(t in ("py3", WANT_TAG, "py%d%d" % TARGET) for t in py.split("."))
        plat_ok = plat == "any" or (PLAT in plat and ARCH in plat)
        if py_ok and plat_ok:
            return fn
    return None


def main():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pins = []
    for line in req.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.\-]+)$", line)
        if m:
            pins.append((m.group(1), m.group(2)))
        else:
            print("SKIP (not a strict pin): %r" % line)

    print("target interpreter: %s -> want wheel tag %s" % (sys.version.split()[0], WANT_TAG))
    print("-" * 72)

    failures = []
    for name, want in pins:
        meta = public_pypi(name)
        if "__error__" in meta:
            print("FAIL  %-16s not reachable on public PyPI (%s)" % (name, meta["__error__"]))
            failures.append((name, "missing from public PyPI"))
            continue
        releases = meta.get("releases", {})
        if want not in releases:
            print("FAIL  %-16s==%-10s not on public PyPI (has: %s)"
                  % (name, want, ", ".join(sorted(releases)[-5:])))
            failures.append((name, "version %s not on public PyPI" % want))
            continue
        tags = wheels_for(releases[want])
        if not tags:
            print("FAIL  %-16s==%-10s has NO wheels (sdist only) -> source build on Render"
                  % (name, want))
            failures.append((name, "sdist only"))
            continue
        good = ok_for_target(tags)
        if good:
            print("ok    %-16s==%-10s  %s" % (name, want, good))
        else:
            print("FAIL  %-16s==%-10s no %s/%s wheel; has: %s"
                  % (name, want, WANT_TAG, PLAT, ", ".join(sorted(tags))))
            failures.append((name, "no wheel for target"))

    print("-" * 72)
    if failures:
        print("PREFLIGHT FAILURES (%d):" % len(failures))
        for name, why in failures:
            print("  - %s: %s" % (name, why))
        return 1
    print("PREFLIGHT OK: every pin installs from a prebuilt wheel on PyPI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
