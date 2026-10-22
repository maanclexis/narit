"""Doctrine lookup and traversal endpoints."""

from typing import Optional
from fastapi import APIRouter, Query
from api.db import get_driver, get_database
from api.schemas import Doctrine, Case

router = APIRouter(prefix="/doctrines", tags=["doctrines"])

DB = get_database


@router.get("", response_model=list[Doctrine])
def list_doctrines(
    domain: Optional[str] = Query(None, description="Filter by domain (evidence, procedure, substantive)"),
):
    """List all doctrines, optionally filtered by domain."""
    if domain:
        records, _, _ = get_driver().execute_query(
            "MATCH (d:Doctrine {domain: $domain}) RETURN properties(d) AS p ORDER BY d.name",
            domain=domain,
            database_=DB(),
        )
    else:
        records, _, _ = get_driver().execute_query(
            "MATCH (d:Doctrine) RETURN properties(d) AS p ORDER BY d.name",
            database_=DB(),
        )
    return [r["p"] for r in records]


@router.get("/{name}/cases")
def cases_for_doctrine(name: str):
    """Cases that establish or apply a doctrine."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH (c:Case)-[r:ESTABLISHES|APPLIES]->(d:Doctrine {name: $name})
        RETURN properties(c) AS case, type(r) AS relationship,
               r.year AS year
        ORDER BY c.judgment_date DESC
        """,
        name=name,
        database_=DB(),
    )
    return [dict(r) for r in records]
