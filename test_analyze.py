import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


class _EmptySession:
    """Stand-in for a Neo4j session that yields zero records."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def run(self, *args, **kwargs):
        return iter([])


def _build_app(monkeypatch):
    # Force the no-LLM path so extraction falls through to fallback rules.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    import api.analyze as analyze_mod
    importlib.reload(analyze_mod)

    # Simulate Neo4j returning nothing (relevancy gate empties the result set)
    # without a live Aura round-trip. Patch after reload so the re-imported
    # symbol is the one we override.
    monkeypatch.setattr(analyze_mod, "get_session", lambda: _EmptySession())

    app = FastAPI()
    app.include_router(analyze_mod.router)
    return TestClient(app)


def test_no_match_for_non_legal_prompt(monkeypatch):
    client = _build_app(monkeypatch)
    r = client.post("/analyze", json={"facts": "I want to bake a cake"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_match"
    assert body["sections"] == []
    assert body["reasoning_steps"] == []
    # Fallback table runs before Neo4j and is preserved on the no_match branch
    assert body["relevancy_table"] != []


def test_llm_fallback_when_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    import api.analyze as analyze_mod
    importlib.reload(analyze_mod)
    kws = analyze_mod.extract_keywords("The tenant breached the lease agreement")
    assert isinstance(kws, list) and len(kws) > 0
