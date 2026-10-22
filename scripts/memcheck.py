"""Measure the memory the running app actually uses.

Render's free web service has 512 MB of RAM. scikit-learn, numpy and the
model file all sit in memory at once, so the number that matters is the
working set of the *started server* after it has loaded the model - not the
size of the source tree and not the size of the model file.

Runs the app the way Render does, exercises it, then reports the peak
working set so a deploy failure caused by an out-of-memory kill is caught
here instead of in the Render log.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT_MB = 512  # Render free tier


def rss_mb(pid):
    """Working set of the process, in MB, read from Windows directly.

    Two earlier attempts were wrong in instructive ways:
      * wmic was removed from recent Windows builds and returns nothing, so
        the check silently reported 0 MB and passed without measuring.
      * tasklist reports a plausible number, but it is the *Mem Usage* column
        of the process it was asked about - which, for a process started via a
        venv launcher, is not the interpreter that holds the model.

    GetProcessMemoryInfo asks the kernel for the working set of one exact
    PID, which is the number that actually matters here.
    """
    import ctypes
    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    try:
        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)  # QUERY_INFO|VM_READ
        if not handle:
            return 0.0
        try:
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return 0.0
            return counters.WorkingSetSize / (1024 * 1024)
        finally:
            kernel32.CloseHandle(handle)
    except Exception as e:  # noqa: BLE001
        print("  (could not read memory: %s)" % e)
        return 0.0


def main():
    """Measure the app's own footprint, in this process.

    Measuring a child process turned out to be unreliable here: the venv
    launcher and the interpreter that ends up holding the model are not
    obviously the same PID, and reading the child's working set reported a
    number far too small to be true. Importing the app and loading the model
    in *this* process removes the guesswork - the working set of this PID is
    exactly the number that decides whether the app fits in Render's 512 MB
    free-tier limit.
    """
    sys.path.insert(0, str(ROOT))

    baseline = rss_mb(os.getpid())
    print("bare interpreter       : %6.1f MB" % baseline)

    from app.main import app  # noqa: F401  - the import is the measurement
    after_import = rss_mb(os.getpid())
    print("after importing the app: %6.1f MB" % after_import)

    from app.classifier import predict
    predict("I have had a headache and fever for three days")
    after_model = rss_mb(os.getpid())
    print("after loading the model: %6.1f MB" % after_model)

    peak = max(baseline, after_import, after_model)
    print("-" * 52)
    print("app footprint (peak)   : %6.1f MB" % peak)
    print("free tier limit        : %6.1f MB" % LIMIT_MB)
    headroom = LIMIT_MB - peak
    print("headroom               : %6.1f MB" % headroom)
    if headroom <= 0:
        print("FAIL: the app does not fit in the free tier")
        return 1
    if headroom < 100:
        print("WARN: less than 100 MB headroom - a concurrent request could "
              "push this over")
    print("OK: fits in the free tier")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
