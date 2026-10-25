"""Health check endpoint.

Reports node_count for the existing consumers, plus process RSS so the Render
free-tier memory ceiling (512MB) is observable from prod without a dashboard.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter

from api.db import get_driver, get_database

router = APIRouter(tags=["health"])


def _rss_mb() -> float | None:
    """Current process resident set size in MB, or None if unreadable.

    Linux (Render): ru_maxrss is in kilobytes.
    macOS: ru_maxrss is in bytes.
    Windows: no getrusage, so fall back to psapi working set.
    """
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(rss / 1024.0, 1)  # KB -> MB on Linux
    except ImportError:
        pass
    try:
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
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
                ("PrivateUsage", ctypes.c_size_t),
            ]

        c = _PMC()
        c.cb = ctypes.sizeof(c)
        h = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb)
        return round(c.WorkingSetSize / 1024 / 1024, 1)
    except Exception:
        return None


@router.get("/health")
def health():
    driver = get_driver()
    driver.verify_connectivity()
    records, _, _ = driver.execute_query(
        "MATCH (n) RETURN count(n) AS c",
        database_=get_database(),
    )
    return {
        "status": "ok",
        "node_count": records[0]["c"],
        "rss_mb": _rss_mb(),
        "rss_limit_mb": int(os.getenv("RSS_LIMIT_MB", "512")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
