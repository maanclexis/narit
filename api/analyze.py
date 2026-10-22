import os
import re
import concurrent.futures
from fastapi import APIRouter
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

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


STOPWORDS = set(
    """a an the and or but if then of to in on for with by at from as is are was were be been
    being this that these those i me my we our you your he she it they them their his her its
    do does did not no so such than too very can will just don should now want like""".split()
)


def _stopword_keywords(facts: str, limit: int = 5):
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", facts.lower())
    seen, out = set(), []
    for w in words:
        if w in STOPWORDS or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) == limit:
            break
    return out


LLM_PROMPT = (
    "You are a legal search assistant. Extract the 5 most relevant legal keywords "
    "from this fact pattern. Return ONLY a comma-separated list, no other text. "
    "Fact pattern: {facts}"
)


def _call_openai(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=60,
    )
    return resp.choices[0].message.content or ""


def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
    return model.generate_content(prompt).text or ""


def _llm_keywords(facts: str, timeout: float = 3.0):
    """Return list of keywords from LLM, or None if unavailable/failed/timed-out."""
    prompt = LLM_PROMPT.format(facts=facts)
    if os.getenv("OPENAI_API_KEY"):
        fn = _call_openai
    elif os.getenv("GEMINI_API_KEY"):
        fn = _call_gemini
    else:
        return None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn, prompt)
            raw = fut.result(timeout=timeout)
    except Exception:
        return None

    if not raw:
        return None
    terms = [t.strip().lower() for t in raw.split(",") if t.strip()]
    terms = [re.sub(r"[^a-z0-9 \-]", "", t) for t in terms]
    terms = [t for t in terms if t]
    return terms[:5] or None


def extract_keywords(facts: str):
    if not facts or not facts.strip():
        return []
    return _llm_keywords(facts) or _stopword_keywords(facts)


def _query_neo4j(keywords):
    if not keywords: return []
    d=get_driver()
    cy="""MATCH (s:Section) WHERE any(k IN $kw WHERE toLower(coalesce(s.text,'')) CONTAINS k OR toLower(coalesce(s.title,'')) CONTAINS k) OPTIONAL MATCH (s)-[:MAPS_TO]->(t:Section) RETURN s.code AS code,s.number AS number,s.title AS title,t.code AS target_code,t.number AS target_number LIMIT 50"""
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
        if k in seen: continue
        sec={"code":r["code"],"number":r["number"],"title":r.get("title")}
        if r.get("target_code") and r.get("target_number"):
            sec["equivalent"]={"code":r["target_code"],"number":r["target_number"]}
        seen[k]=sec
    secs=list(seen.values())
    if not secs: return {"sections":[],"path":[],"status":"no_match"}
    return {"sections":secs,"path":[x["code"]+" "+x["number"] for x in secs],"status":"ok"}
