"""Unit tests for the ONNX cross-encoder reranker."""

import importlib

import pytest


@pytest.fixture
def reranker_mod():
    import api.reranker as mod
    return mod


def test_model_is_available(reranker_mod):
    assert reranker_mod.is_available() is True


def test_rerank_empty_input(reranker_mod):
    ranked, used = reranker_mod.rerank("anything", [])
    assert ranked == []
    assert used is False


def test_rerank_returns_top_k_and_scores(reranker_mod):
    cands = [
        {"title": "Theft", "text": "Whoever dishonestly takes movable property without consent commits theft.", "score": 40.0},
        {"title": "Cheating", "text": "Whoever by deceiving any person fraudulently induces delivery of property commits cheating.", "score": 38.0},
        {"title": "Hurt", "text": "Whoever voluntarily causes hurt to any person commits an offence.", "score": 36.0},
        {"title": "Murder", "text": "Whoever commits murder shall be punished.", "score": 34.0},
        {"title": "Rape", "text": "Whoever commits rape shall be punished.", "score": 32.0},
        {"title": "Kidnapping", "text": "Whoever kidnaps any person commits an offence.", "score": 30.0},
    ]
    ranked, used = reranker_mod.rerank("someone stole my bike", cands, top_k=3)
    assert used is True
    assert len(ranked) == 3
    for c in ranked:
        assert "bm25_score" in c
        assert "reranker_score" in c
        assert "final_score" in c
        assert 0.0 <= c["final_score"] <= 1.0


def test_rerank_blend_is_deterministic(reranker_mod):
    def _mk():
        return [
            {"title": f"Sec {i}", "text": "Whoever takes movable property commits theft.", "score": 30.0 - i}
            for i in range(5)
        ]
    r1, _ = reranker_mod.rerank("stole bike", _mk(), top_k=5)
    r2, _ = reranker_mod.rerank("stole bike", _mk(), top_k=5)
    assert [c["title"] for c in r1] == [c["title"] for c in r2]
    assert [c["final_score"] for c in r1] == [c["final_score"] for c in r2]


def test_rerank_failsoft_when_model_missing(monkeypatch):
    import api.reranker as mod
    importlib.reload(mod)
    monkeypatch.setenv("RERANKER_MODEL_DIR", "C:\\nonexistent_path_xyz")
    mod._load_attempted = False
    mod._load_failed = False
    mod._session = None
    mod._tokenizer = None
    mod._input_names = []
    assert mod.is_available() is False
    cands = [{"title": "A", "text": "x", "score": 10.0}, {"title": "B", "text": "y", "score": 9.0}]
    ranked, used = mod.rerank("query", cands, top_k=5)
    assert used is False
    assert [c["title"] for c in ranked] == ["A", "B"]
