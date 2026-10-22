import os
import importlib
from fastapi.testclient import TestClient
from fastapi import FastAPI


def _build_app(monkeypatch):
    # Force stopword fallback (no LLM key) for deterministic test
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    import api.analyze as analyze_mod
    importlib.reload(analyze_mod)

    # Neo4j returns nothing for non-legal prompt
    monkeypatch.setattr(analyze_mod, "_query_neo4j", lambda kw: [])

    app = FastAPI()
    app.include_router(analyze_mod.router)
    return TestClient(app)


def test_no_match_for_non_legal_prompt(monkeypatch):
    client = _build_app(monkeypatch)
    r = client.post("/analyze", json={"facts": "I want to bake a cake"})
    assert r.status_code == 200
    body = r.json()
    assert body == {"sections": [], "path": [], "status": "no_match"}


def test_llm_fallback_when_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    import api.analyze as analyze_mod
    importlib.reload(analyze_mod)
    kws = analyze_mod.extract_keywords("The tenant breached the lease agreement")
    assert isinstance(kws, list) and len(kws) > 0
