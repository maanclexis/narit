"""HITL Knowledge Builder — Contribute router."""

from __future__ import annotations

import os
import re
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from api.db import get_driver, get_database

router = APIRouter(tags=["contribute"])


class ProposeRequest(BaseModel):
    text: str


class TargetSection(BaseModel):
    code: str
    number: str


class ProposedNode(BaseModel):
    label: str = "Case"
    properties: dict[str, Any]


class ProposedEdge(BaseModel):
    type: str = "INTERPRETS"
    target_section: TargetSection


class CommitRequest(BaseModel):
    proposed_node: ProposedNode
    proposed_edge: ProposedEdge
    status: Optional[str] = None


def _extract_heuristic(text: str) -> dict[str, Any]:
    """Extract node and target section from text using regex heuristics."""
    clean_text = text.strip()

    # 1. Extract Citation (e.g., State v. Sharma, Kesavananda Bharati v. State of Kerala)
    cite_match = re.search(
        r'(?:in\s+the\s+case\s+of|in\s+case\s+of|case\s+of|matter\s+of)\s+([A-Za-z0-9\.\'\s]+?\s+(?:v\.|vs\.|versus)\s+[A-Za-z0-9\.\'\s]+?(?:\s*\(\d{4}\))?)(?:,|\.|\s+the|\s+where|\s+court|\s*$)',
        clean_text,
        re.IGNORECASE,
    )
    if not cite_match:
        cite_match = re.search(
            r'([A-Z][A-Za-z0-9\.\'\s]+?\s+(?:v\.|vs\.|versus)\s+[A-Z][A-Za-z0-9\.\'\s]+?(?:\s*\(\d{4}\))?)(?:,|\.|\s+the|\s+where|\s+court|\s*$)',
            clean_text,
        )

    if cite_match:
        citation = cite_match.group(1).strip().rstrip(",.;")
    else:
        # Fallback citation
        first_clause = re.split(r'[,;\.]', clean_text)[0].strip()
        citation = first_clause if len(first_clause) < 50 else clean_text[:45] + "..."

    # 2. Extract Title / Topic
    m_rule = re.search(
        r'(?:ruled\s+on|held\s+that|regarding|concerning|involving|about)\s+([^,\.]+)',
        clean_text,
        re.IGNORECASE,
    )
    if m_rule:
        topic = m_rule.group(1).strip()
        topic = re.sub(r'\s+under\s+section.*', '', topic, flags=re.IGNORECASE).strip()
        title = f"Ruling on {topic.capitalize()}"
    else:
        # Check standard crime keywords
        for kw in ["murder", "theft", "assault", "cheating", "defamation", "kidnapping", "rape", "extortion", "robbery", "grievous hurt"]:
            if re.search(r'\b' + kw + r'\b', clean_text, re.IGNORECASE):
                title = f"Judgment on {kw.capitalize()}"
                break
        else:
            title = "New Judgment"

    # 3. Extract Section Number & Code Hint
    m_sec = re.search(r'\b(?:section|sec\.?|§)\s*(\d+[A-Za-z0-9\(\)]*)', clean_text, re.IGNORECASE)
    section_number = m_sec.group(1).strip() if m_sec else None

    m_code = re.search(r'\b(IPC|BNS|BNSS|BSA)\b', clean_text, re.IGNORECASE)
    code_hint = m_code.group(1).upper() if m_code else None

    return {
        "label": "Case",
        "citation": citation,
        "title": title,
        "section_number": section_number,
        "code_hint": code_hint,
    }


def _verify_target_section(code_hint: str | None, number: str, text: str) -> dict[str, str] | None:
    """Verify in Neo4j if target section exists. Return code and number."""
    driver = get_driver()
    db = get_database()
    with driver.session(database=db) as session:
        # If code hint exists, try exact match first
        if code_hint:
            result = session.run(
                "MATCH (s:Section) WHERE toUpper(s.code) = toUpper($code) AND s.number = $number RETURN s.code AS code, s.number AS number, s.title AS title LIMIT 1",
                code=code_hint,
                number=number,
            ).data()
            if result:
                return {"code": result[0]["code"], "number": result[0]["number"]}

        # Otherwise find candidate sections by number
        results = session.run(
            "MATCH (s:Section) WHERE s.number = $number RETURN s.code AS code, s.number AS number, s.title AS title",
            number=number,
        ).data()

        if not results:
            return None

        # If multiple candidates, rank by keyword overlap with text
        text_lower = text.lower()
        for r in results:
            r_title = (r.get("title") or "").lower()
            if any(w in r_title for w in ["murder", "theft", "hurt", "cheat", "assault"] if w in text_lower):
                return {"code": r["code"], "number": r["number"]}

        # Default to IPC if available, else first
        for r in results:
            if r["code"].upper() == "IPC":
                return {"code": r["code"], "number": r["number"]}
        for r in results:
            if r["code"].upper() == "BNS":
                return {"code": r["code"], "number": r["number"]}

        return {"code": results[0]["code"], "number": results[0]["number"]}


@router.post("/propose")
def propose(req: ProposeRequest):
    """Analyze input text and propose a new graph node and relationship."""
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Input text cannot be empty.")

    extracted = _extract_heuristic(req.text)

    sec_num = extracted["section_number"]
    if not sec_num:
        # Default fallback if no explicit section number mentioned
        sec_num = "302"

    target_sec = _verify_target_section(extracted["code_hint"], sec_num, req.text)
    if not target_sec:
        # If not verified in DB, fallback to code_hint or IPC with the extracted number
        target_sec = {"code": extracted["code_hint"] or "IPC", "number": sec_num}

    payload = {
        "proposed_node": {
            "label": extracted["label"],
            "properties": {
                "citation": extracted["citation"],
                "title": extracted["title"],
            },
        },
        "proposed_edge": {
            "type": "INTERPRETS",
            "target_section": {
                "code": target_sec["code"],
                "number": target_sec["number"],
            },
        },
        "status": "ready_for_review",
    }
    return payload


@router.post("/commit")
def commit(req: CommitRequest):
    """Commit proposed node and edge permanently into Neo4j."""
    node = req.proposed_node
    edge = req.proposed_edge

    label = re.sub(r"[^A-Za-z0-9_]", "", node.label) or "Case"
    rel_type = re.sub(r"[^A-Za-z0-9_]", "", edge.type) or "INTERPRETS"

    citation = node.properties.get("citation", "").strip()
    title = node.properties.get("title", "").strip()
    target_code = edge.target_section.code.strip()
    target_number = edge.target_section.number.strip()

    if not citation:
        raise HTTPException(status_code=400, detail="Node citation cannot be empty.")

    case_id = "CASE_" + re.sub(r"[^A-Za-z0-9]+", "_", citation).strip("_").upper()

    driver = get_driver()
    db = get_database()

    cypher = f"""
    MATCH (s:Section)
    WHERE toUpper(s.code) = toUpper($target_code) AND s.number = $target_number
    MERGE (n:{label} {{citation: $citation}})
    SET n.title = $title,
        n.case_name = coalesce(n.case_name, $citation),
        n.id = coalesce(n.id, $case_id)
    MERGE (n)-[r:{rel_type}]->(s)
    RETURN n.citation AS citation, s.code AS code, s.number AS number
    """

    with driver.session(database=db) as session:
        result = session.run(
            cypher,
            target_code=target_code,
            target_number=target_number,
            citation=citation,
            title=title,
            case_id=case_id,
        ).data()

        if not result:
            # If section was not found, create relation with MERGE on Section
            fallback_cypher = f"""
            MERGE (s:Section {{code: $target_code, number: $target_number}})
            MERGE (n:{label} {{citation: $citation}})
            SET n.title = $title,
                n.case_name = coalesce(n.case_name, $citation),
                n.id = coalesce(n.id, $case_id)
            MERGE (n)-[r:{rel_type}]->(s)
            RETURN n.citation AS citation, s.code AS code, s.number AS number
            """
            result = session.run(
                fallback_cypher,
                target_code=target_code,
                target_number=target_number,
                citation=citation,
                title=title,
                case_id=case_id,
            ).data()

    return {"status": "success", "message": "Graph updated permanently."}
