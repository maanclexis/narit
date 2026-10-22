"""Pydantic response models for the NARIT Legal Graph API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


# ── Health ────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    node_count: int
    timestamp: str


# ── Statutes & Sections ──────────────────────────────────────────────
class Statute(BaseModel):
    id: str
    name: str
    full_title: Optional[str] = None
    year: Optional[int] = None
    jurisdiction: Optional[str] = None
    status: Optional[str] = None


class Section(BaseModel):
    id: str
    number: str
    title: Optional[str] = None
    text: Optional[str] = None
    statute_id: str
    offence_type: Optional[str] = None
    punishment: Optional[str] = None
    cognizable: Optional[bool] = None
    bailable: Optional[bool] = None


class SectionMapping(BaseModel):
    source: Section
    target: Section
    mapping_type: str
    notes: Optional[str] = None


# ── Cases ─────────────────────────────────────────────────────────────
class Case(BaseModel):
    id: str
    citation: Optional[str] = None
    case_name: Optional[str] = None
    court: Optional[str] = None
    judgment_date: Optional[str] = None
    bench: Optional[str] = None
    holding_summary: Optional[str] = None


class Citation(BaseModel):
    case: Case
    treatment: Optional[str] = None


# ── Doctrines ─────────────────────────────────────────────────────────
class Doctrine(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = None


# ── Procedures ────────────────────────────────────────────────────────
class Procedure(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    mandatory: Optional[bool] = None
    sequence_order: Optional[int] = None
    consequence_of_noncompliance: Optional[str] = None


# ── FIR ───────────────────────────────────────────────────────────────
class FIR(BaseModel):
    id: str
    fir_number: str
    police_station: Optional[str] = None
    date_filed: Optional[str] = None
    offence_summary: Optional[str] = None
    narcotic_type: Optional[str] = None
    quantity: Optional[str] = None
    status: Optional[str] = None


class ComplianceStep(BaseModel):
    procedure: Procedure
    compliant: Optional[bool] = None
    note: Optional[str] = None
