import os
import re
import warnings
import concurrent.futures
from fastapi import APIRouter
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
warnings.filterwarnings("ignore", category=FutureWarning)

router = APIRouter()

# ----- Neo4j driver (adjust import to your existing setup) -----
try:
    from api.db import get_driver  # existing project driver factory
except Exception:  # pragma: no cover
    from neo4j import GraphDatabase

    def get_driver():
        return GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "neo4j")),
        )


class AnalyzeRequest(BaseModel):
    facts: str


LLM_PROMPT = (
    "You are an Indian criminal law expert. Read this fact pattern and extract the "
    "specific legal concepts (e.g., 'theft', 'cheating', 'assault'). Do not use generic words. "
    "Return ONLY a comma-separated list of legal concepts. Fact pattern: {facts}"
)


def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai
    try:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"], transport="rest")
    except TypeError:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-3.5-flash"))
    return model.generate_content(prompt).text or ""


def _llm_keywords(facts: str, timeout: float = 3.0):
    """Return list of keywords from Gemini LLM, or None if unavailable/failed/timed-out."""
    if not os.getenv("GEMINI_API_KEY"):
        return None

    prompt = LLM_PROMPT.format(facts=facts)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_call_gemini, prompt)
            raw = fut.result(timeout=max(timeout, 10.0))
    except Exception:
        return None

    if not raw:
        return None
    terms = [t.strip().lower() for t in raw.split(",") if t.strip()]
    terms = [re.sub(r"[^a-z0-9 \-]", "", t) for t in terms]
    terms = [t for t in terms if t]
    return terms[:5] or None


def fallback_extract(facts):
    facts = facts.lower()
    concepts = []
    if any(w in facts for w in ["stole", "took", "phone", "motorcycle", "bike", "snatched"]): concepts.append("theft")
    if any(w in facts for w in ["hit", "stick", "broke", "arm", "punch", "slap", "hurt"]): concepts.append("hurt")
    if any(w in facts for w in ["tricked", "money", "scam", "fraud", "cheated"]): concepts.append("cheating")
    return concepts if concepts else [facts]


def extract_keywords(facts: str):
    if not facts or not facts.strip():
        return []
    llm_res = _llm_keywords(facts)
    if llm_res:
        return llm_res
    return fallback_extract(facts)


def _query_neo4j(keywords):
    if not keywords: return []
    d=get_driver()
    cy="""MATCH (s:Section) WHERE any(k IN $kw WHERE toLower(coalesce(s.text,'')) CONTAINS k OR toLower(coalesce(s.title,'')) CONTAINS k) OPTIONAL MATCH (s)-[:MAPS_TO]->(t:Section) OPTIONAL MATCH (c:Case)-[:INTERPRETS]->(s) OPTIONAL MATCH (ct:Case)-[:INTERPRETS]->(t) RETURN s.code AS code, s.number AS number, s.title AS title, s.text AS text, t.code AS target_code, t.number AS target_number, coalesce(c.citation, ct.citation) AS case_citation, coalesce(c.title, ct.title) AS case_title, coalesce(c.summary, ct.summary) AS case_summary LIMIT 50"""
    with d.session() as ss: return ss.run(cy,kw=keywords).data()


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    kw=extract_keywords(req.facts)
    try: rows=_query_neo4j(kw)
    except Exception: rows=[]
    seen={}
    for r in rows:
        if not r.get("number"): continue
        k=(r["code"],r["number"])
        if k not in seen:
            sec={"code":r["code"],"number":r["number"],"title":r.get("title"),"text":r.get("text"),"cases":[]}
            if r.get("target_code") and r.get("target_number"):
                sec["equivalent"]={"code":r["target_code"],"number":r["target_number"]}
            seen[k]=sec
        else:
            sec=seen[k]
        if r.get("case_citation"):
            case_obj={
                "citation": r["case_citation"],
                "title": r.get("case_title", ""),
                "summary": r.get("case_summary", "")
            }
            if case_obj not in sec["cases"]:
                sec["cases"].append(case_obj)
    secs=list(seen.values())
    if not secs: return {"sections":[],"path":[],"status":"no_match"}
    secs.sort(key=lambda x: len(x.get("cases", [])), reverse=True)
    return {"sections":secs,"path":[x["code"]+" "+x["number"] for x in secs],"status":"ok"}
