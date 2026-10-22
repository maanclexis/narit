"""FIR analysis and compliance check endpoints."""

from fastapi import APIRouter, HTTPException
from api.db import get_driver, get_database
from api.schemas import FIR, Section, ComplianceStep

router = APIRouter(prefix="/firs", tags=["firs"])

DB = get_database


@router.get("/{fir_number}", response_model=FIR)
def get_fir(fir_number: str):
    """Get an FIR by its number."""
    records, _, _ = get_driver().execute_query(
        "MATCH (f:FIR {fir_number: $fn}) RETURN properties(f) AS p",
        fn=fir_number,
        database_=DB(),
    )
    if not records:
        raise HTTPException(404, f"FIR {fir_number} not found")
    return records[0]["p"]


@router.get("/{fir_number}/sections", response_model=list[Section])
def fir_charged_sections(fir_number: str):
    """Sections the FIR is charged under."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH (f:FIR {fir_number: $fn})-[:CHARGED_UNDER]->(s:Section)
        RETURN properties(s) AS p ORDER BY s.number
        """,
        fn=fir_number,
        database_=DB(),
    )
    return [r["p"] for r in records]


@router.get("/{fir_number}/compliance")
def compliance_check(fir_number: str):
    """Check mandatory procedure compliance for an FIR.

    Walks FIR → TRIGGERS → Procedure → PRECEDES chain and flags
    whether each mandatory step has been recorded.
    """
    records, _, _ = get_driver().execute_query(
        """
        MATCH (f:FIR {fir_number: $fn})-[t:TRIGGERS]->(start:Procedure)
        OPTIONAL MATCH path = (start)-[:PRECEDES*0..20]->(step:Procedure)
        WITH step, length(path) AS depth, t.deadline_days AS deadline
        ORDER BY depth
        RETURN properties(step) AS procedure, step.mandatory AS mandatory,
               deadline,
               step.consequence_of_noncompliance AS consequence
        """,
        fn=fir_number,
        database_=DB(),
    )
    if not records:
        raise HTTPException(404, f"FIR {fir_number} not found or has no triggered procedures")

    steps = []
    for r in records:
        steps.append({
            "procedure": r["procedure"],
            "mandatory": r["mandatory"],
            "deadline_days": r["deadline"],
            "consequence_of_noncompliance": r["consequence"],
        })
    return {"fir_number": fir_number, "procedure_chain": steps}
