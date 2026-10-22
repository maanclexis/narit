"""Health check endpoint."""

from datetime import datetime, timezone
from fastapi import APIRouter
from api.db import get_driver, get_database

router = APIRouter(tags=["health"])


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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
