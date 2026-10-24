"""Statute & Section endpoints."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from api.db import get_driver, get_database
from api.schemas import Statute, Section, SectionMapping

router = APIRouter(prefix="/statutes", tags=["statutes"])

DB = get_database


@router.get("", response_model=list[Statute])
def list_statutes():
    """List all statutes, optionally filtered by jurisdiction."""
    records, _, _ = get_driver().execute_query(
        "MATCH (s:Statute) RETURN properties(s) AS p ORDER BY s.year DESC",
        database_=DB(),
    )
    return [r["p"] for r in records]


@router.get("/{name}/sections", response_model=list[Section])
def sections_of_statute(name: str):
    """Return all sections belonging to a statute."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH (st:Statute {name: $name})<-[:BELONGS_TO]-(s:Section)
        RETURN properties(s) AS p ORDER BY s.number
        """,
        name=name,
        database_=DB(),
    )
    if not records:
        # Try via statute_id foreign key
        records, _, _ = get_driver().execute_query(
            """
            MATCH (s:Section) WHERE s.statute_id = $name
            RETURN properties(s) AS p ORDER BY s.number
            """,
            name=name,
            database_=DB(),
        )
    return [r["p"] for r in records]


# ── Section detail ────────────────────────────────────────────────────

section_router = APIRouter(prefix="/sections", tags=["sections"])


@section_router.get("/{section_id}", response_model=Section)
def get_section(section_id: str):
    """Get a section by its unique ID."""
    records, _, _ = get_driver().execute_query(
        "MATCH (s:Section {id: $id}) RETURN properties(s) AS p",
        id=section_id,
        database_=DB(),
    )
    if not records:
        raise HTTPException(404, f"Section {section_id} not found")
    return records[0]["p"]


@section_router.get("/{section_id}/cases", response_model=list[dict])
def cases_for_section(section_id: str):
    """Cases that were decided under or interpret a given section."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH (c:Case)-[r:DECIDED_UNDER|INTERPRETS]->(s:Section {id: $id})
        RETURN properties(c) AS case, type(r) AS relationship,
               r.role AS role, r.paragraph AS paragraph
        ORDER BY c.judgment_date DESC
        """,
        id=section_id,
        database_=DB(),
    )
    return [dict(r) for r in records]


@section_router.get("/{section_id}/references", response_model=list[dict])
def references_for_section(section_id: str):
    """Sections cross-referenced by the given section (parsed from Bare Act text)."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH (s:Section {id: $id})-[r:REFERENCES]->(t:Section)
        RETURN t.uid AS uid, t.code AS code, t.number AS number,
               t.title AS title, r.raw_text AS raw_text,
               r.pattern_type AS pattern_type, r.context AS context
        ORDER BY t.number
        """,
        id=section_id,
        database_=DB(),
    )
    return [dict(r) for r in records]


@section_router.get("/{section_id}/mapped", response_model=list[SectionMapping])
def cross_statute_mappings(section_id: str):
    """Find cross-statute mappings (e.g. IPC → BNS)."""
    records, _, _ = get_driver().execute_query(
        """
        MATCH (a:Section {id: $id})-[m:MAPS_TO]->(b:Section)
        RETURN properties(a) AS source, properties(b) AS target,
               m.mapping_type AS mapping_type, m.notes AS notes
        UNION
        MATCH (b:Section)-[m:MAPS_TO]->(a:Section {id: $id})
        RETURN properties(b) AS source, properties(a) AS target,
               m.mapping_type AS mapping_type, m.notes AS notes
        """,
        id=section_id,
        database_=DB(),
    )
    return [dict(r) for r in records]
