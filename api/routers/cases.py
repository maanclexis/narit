"""Case search and citation network endpoints."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from api.db import get_driver, get_database
from api.schemas import Case, Citation

router = APIRouter(prefix="/cases", tags=["cases"])

DB = get_database


@router.get("", response_model=list[Case])
def search_cases(
    court: Optional[str] = Query(None, description="Filter by court"),
    q: Optional[str] = Query(None, description="Full-text search in case_name or holding_summary"),
    limit: int = Query(25, ge=1, le=100),
):
    """Search cases by court, keyword, or date range."""
    clauses, params = ["MATCH (c:Case)"], {}

    wheres = []
    if court:
        wheres.append("c.court = $court")
        params["court"] = court
    if q:
        wheres.append("(c.case_name CONTAINS $q OR c.holding_summary CONTAINS $q)")
        params["q"] = q

    if wheres:
        clauses.append("WHERE " + " AND ".join(wheres))
    clauses.append("RETURN properties(c) AS p ORDER BY c.judgment_date DESC LIMIT $limit")
    params["limit"] = limit

    records, _, _ = get_driver().execute_query(
        "\n".join(clauses), database_=DB(), **params
    )
    return [r["p"] for r in records]


@router.get("/{case_id}", response_model=Case)
def get_case(case_id: str):
    """Get a case by its unique ID."""
    records, _, _ = get_driver().execute_query(
        "MATCH (c:Case {id: $id}) RETURN properties(c) AS p",
        id=case_id,
        database_=DB(),
    )
    if not records:
        raise HTTPException(404, f"Case {case_id} not found")
    return records[0]["p"]


@router.get("/{case_id}/cites", response_model=list[Citation])
def outbound_citations(case_id: str):
    """Cases cited by this case, with treatment (followed/distinguished/overruled)."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH (c:Case {id: $id})-[r:CITES]->(cited:Case)
        RETURN properties(cited) AS case, r.treatment AS treatment
        ORDER BY cited.judgment_date DESC
        """,
        id=case_id,
        database_=DB(),
    )
    return [dict(r) for r in records]


@router.get("/{case_id}/cited-by", response_model=list[Citation])
def inbound_citations(case_id: str):
    """Cases that cite this case."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH (citing:Case)-[r:CITES]->(c:Case {id: $id})
        RETURN properties(citing) AS case, r.treatment AS treatment
        ORDER BY citing.judgment_date DESC
        """,
        id=case_id,
        database_=DB(),
    )
    return [dict(r) for r in records]
