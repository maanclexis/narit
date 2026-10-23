import os
import re
import json
from fastapi import APIRouter
from pydantic import BaseModel
import google.generativeai as genai
from api.db import get_session

router = APIRouter()


class AnalyzeRequest(BaseModel):
    facts: str
    act_filter: str | None = None


ANALYSE_SYSTEM_PROMPT = """You are a legal concept analyzer for Indian Statutory Law.
STRICT RULE: Never generate legal advice or cite section numbers. Only analyze the input and rank search keywords.

Given the user's fact pattern:
1. 'input_understanding': A 1-sentence legal characterization identifying Actor, Act, and Harm/Effect.
2. 'relevancy_table': Extract 3 to 5 search rows ordered from highest to lowest relevancy (0.10 to 1.00).
   - 'concept': The formal legal offence/concept name.
   - 'bare_act_terms': 2 to 3 exact archaic/statutory words used in Indian Bare Acts.
   - 'relevancy': Float score between 0.10 and 1.00.
   - 'rationale': 8-word reason why this keyword applies.

Output ONLY valid raw JSON matching this exact structure:
{
  "input_understanding": "...",
  "relevancy_table": [
    {"concept": "...", "bare_act_terms": ["...","..."], "relevancy": 0.9, "rationale": "..."}
  ]
}"""


_model = None
if os.getenv("GEMINI_API_KEY"):
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"), transport="rest")
    _model = genai.GenerativeModel(
        model_name=os.getenv("GEMINI_MODEL", "gemini-1.5-pro-latest"),
        system_instruction=ANALYSE_SYSTEM_PROMPT,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.1,
        },
    )


_LUCENE_RESERVED = re.compile(r'[+\-&|!(){}\[\]^"~*?:\\/]')


def sanitize_lucene_term(term: str) -> str:
    if not term:
        return ""
    cleaned = _LUCENE_RESERVED.sub(' ', term)
    return " ".join(cleaned.split()).strip()


def build_lucene_row(row: dict) -> dict:
    concept = sanitize_lucene_term(row.get("concept", ""))
    terms = [sanitize_lucene_term(t) for t in row.get("bare_act_terms", []) if t]
    terms = [t for t in terms if t]
    phrase_clauses = [f'"{t}"^2.0' for t in [concept] + terms if t]
    word_clauses = [t for t in [concept] + terms if t]
    return {
        "concept": concept,
        "bare_act_terms": terms,
        "relevancy": float(row.get("relevancy", 0.5)),
        "rationale": row.get("rationale", ""),
        "lucene_query": " OR ".join(phrase_clauses + word_clauses) or concept,
    }


_FALLBACK_RULES = [
    (["stole", "took", "snatched", "phone", "motorcycle", "theft"],
     {"concept": "theft", "bare_act_terms": ["movable property", "dishonestly", "takes"],
      "relevancy": 0.9, "rationale": "taking movable property without consent"}),
    (["hit", "stick", "broke", "arm", "hurt", "beat", "assault"],
     {"concept": "hurt", "bare_act_terms": ["voluntarily causing hurt", "bodily pain", "injury"],
      "relevancy": 0.9, "rationale": "causing bodily pain or injury"}),
    (["tricked", "money", "scam", "cheated", "fraud", "deceived"],
     {"concept": "cheating", "bare_act_terms": ["deceives", "fraudulently", "dishonestly induces"],
      "relevancy": 0.9, "rationale": "fraudulent inducement to deliver property"}),
    (["wrong medicine", "medical", "chemist", "prescription", "doctor", "hospital", "dispens"],
     {"concept": "medical preparation", "bare_act_terms": ["medical preparation", "negligent act", "death"],
      "relevancy": 0.9, "rationale": "negligent medical act causing harm"}),
]


def _fallback_table(facts: str) -> list[dict]:
    facts_lower = facts.lower()
    matched = [row for kws, row in _FALLBACK_RULES if any(k in facts_lower for k in kws)]
    if not matched:
        matched = [row for _, row in _FALLBACK_RULES[:2]]
    return matched


_CYPHER = """
MERGE (hb:_Heartbeat {id: 1}) SET hb.last_active = timestamp()
WITH 1 AS ignored

UNWIND $relevancy_table AS kw
CALL db.index.fulltext.queryNodes('sectionSearch', kw.lucene_query) YIELD node AS hit, score AS bm25_score

WITH kw, hit, bm25_score,
     CASE WHEN toLower(hit.title) CONTAINS toLower(kw.concept) THEN 1.5 ELSE 1.0 END AS title_boost
WITH kw, hit, round(bm25_score, 2) AS lucene_score,
     round(kw.relevancy * bm25_score * title_boost, 3) AS weighted_score
WHERE weighted_score > 0.40

OPTIONAL MATCH (hit)-[:MAPS_TO]->(forward_target:Section)
OPTIONAL MATCH (backward_source:Section)-[:MAPS_TO]->(hit)

WITH kw, hit, lucene_score, weighted_score,
     COALESCE(backward_source, hit) AS primary_sec,
     CASE WHEN backward_source IS NOT NULL THEN hit ELSE forward_target END AS mapped_bns

ORDER BY weighted_score DESC
WITH primary_sec, mapped_bns,
     collect({
         trigger_concept: kw.concept,
         bare_act_terms: kw.bare_act_terms,
         keyword_relevancy: kw.relevancy,
         lucene_bm25: lucene_score,
         final_weighted_score: weighted_score,
         rationale: kw.rationale
     })[0] AS winning_trigger,
     max(weighted_score) AS top_pair_score
ORDER BY top_pair_score DESC
LIMIT 5

WITH primary_sec, mapped_bns, winning_trigger, top_pair_score
WHERE $act_filter IS NULL OR primary_sec.statute_role = $act_filter

OPTIONAL MATCH (c:Case)-[:INTERPRETS]->(s:Section)
WHERE s = primary_sec OR s = mapped_bns

RETURN primary_sec.code AS code,
       primary_sec.number AS number,
       primary_sec.title AS title,
       primary_sec.text AS text,
       mapped_bns.code AS bns_code,
       mapped_bns.number AS bns_number,
       mapped_bns.title AS bns_title,
       mapped_bns.text AS bns_text,
       collect(DISTINCT {citation: c.citation, title: c.title, summary: c.summary}) AS cases,
       winning_trigger AS reasoning_step,
       top_pair_score AS score
ORDER BY score DESC
"""


@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    understanding = ""
    relevancy_table_raw: list[dict] = []

    if _model:
        try:
            resp = _model.generate_content(f"Fact pattern: {req.facts}")
            data = json.loads(resp.text)
            understanding = data.get("input_understanding", "") or ""
            relevancy_table_raw = data.get("relevancy_table", []) or []
        except Exception as e:
            print(f"Gemini error: {e}")

    if not relevancy_table_raw:
        relevancy_table_raw = _fallback_table(req.facts)

    relevancy_table = [build_lucene_row(r) for r in relevancy_table_raw if r.get("concept")]
    if not relevancy_table:
        return {
            "sections": [], "path": [], "reasoning_steps": [],
            "understanding": understanding, "relevancy_table": [],
            "status": "no_match",
        }

    with get_session() as session:
        result = session.run(_CYPHER, relevancy_table=relevancy_table, act_filter=req.act_filter)
        records = [record.data() for record in result]

    if not records:
        return {
            "sections": [], "path": [], "reasoning_steps": [],
            "understanding": understanding, "relevancy_table": relevancy_table,
            "status": "no_match",
        }

    path: list[str] = [f"Input: {req.facts}"]
    if understanding:
        path.append(f"Understanding: {understanding}")
    for r in relevancy_table:
        path.append(f"Keyword: {r['concept']} (relevancy={r['relevancy']:.2f})")

    reasoning_steps = []
    for rec in records:
        trig = rec.get("reasoning_step") or {}
        path.append(f"Matched: {rec['code']} {rec['number']} â€” {rec['title']}")
        if rec.get("bns_code"):
            path.append(f"Equivalent: {rec['bns_code']} {rec['bns_number']} â€” {rec.get('bns_title','')}")
        reasoning_steps.append({
            "trigger": trig.get("trigger_concept"),
            "bare_act_terms": trig.get("bare_act_terms"),
            "keyword_relevancy": trig.get("keyword_relevancy"),
            "lucene_bm25": trig.get("lucene_bm25"),
            "final_score": trig.get("final_weighted_score"),
            "rationale": trig.get("rationale"),
            "primary": {"code": rec.get("code"), "number": rec.get("number"), "title": rec.get("title")},
            "mapped": (
                {"code": rec.get("bns_code"), "number": rec.get("bns_number"), "title": rec.get("bns_title")}
                if rec.get("bns_code") else None
            ),
            "cases": rec.get("cases", []),
        })

    return {
        "sections": records,
        "path": path,
        "reasoning_steps": reasoning_steps,
        "understanding": understanding,
        "relevancy_table": relevancy_table,
        "status": "success",
    }


def fallback_extract(facts: str) -> list[str]:
    facts_lower = facts.lower()
    concepts = []
    if any(w in facts_lower for w in ["stole", "took", "phone", "motorcycle", "bike", "snatched"]):
        concepts.append("theft")
    if any(w in facts_lower for w in ["hit", "stick", "broke", "arm", "punch", "slap", "hurt"]):
        concepts.append("hurt")
    if any(w in facts_lower for w in ["tricked", "money", "scam", "fraud", "cheated"]):
        concepts.append("cheating")
    return concepts if concepts else [facts]


def extract_keywords(facts: str) -> list[str]:
    if not facts or not facts.strip():
        return []
    if os.getenv("GEMINI_API_KEY"):
        try:
            m = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-pro-latest"))
            resp = m.generate_content(f"Extract legal concepts: {facts}")
            raw = resp.text or ""
            terms = [t.strip().lower() for t in raw.split(",") if t.strip()]
            terms = [re.sub(r"[^a-z0-9 \-]", "", t) for t in terms]
            terms = [t for t in terms if t]
            if terms:
                return terms[:5]
        except Exception:
            pass
    return fallback_extract(facts)
