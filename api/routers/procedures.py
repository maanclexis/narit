"""Procedure chain walking endpoints."""

from fastapi import APIRouter, HTTPException
from api.db import get_driver, get_database
from api.schemas import Procedure

router = APIRouter(prefix="/procedures", tags=["procedures"])

DB = get_database


@router.get("/{proc_id}", response_model=Procedure)
def get_procedure(proc_id: str):
    """Get a procedure by ID."""
    records, _, _ = get_driver().execute_query(
        "MATCH (p:Procedure {id: $id}) RETURN properties(p) AS p",
        id=proc_id,
        database_=DB(),
    )
    if not records:
        raise HTTPException(404, f"Procedure {proc_id} not found")
    return records[0]["p"]


@router.get("/{proc_id}/chain", response_model=list[Procedure])
def procedure_chain(proc_id: str):
    """Walk the PRECEDES chain from a starting procedure, returning the ordered sequence."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH path = (start:Procedure {id: $id})-[:PRECEDES*0..20]->(step:Procedure)
        WITH step, length(path) AS depth
        ORDER BY depth
        RETURN properties(step) AS p
        """,
        id=proc_id,
        database_=DB(),
    )
    if not records:
        raise HTTPException(404, f"Procedure {proc_id} not found")
    return [r["p"] for r in records]


@router.get("/{proc_id}/required-by")
def required_by_section(proc_id: str):
    """Which statutory sections mandate this procedure."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH (p:Procedure {id: $id})-[:REQUIRES]->(s:Section)
        RETURN properties(s) AS section
        """,
        id=proc_id,
        database_=DB(),
    )
    return [r["section"] for r in records]
