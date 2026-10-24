"""Tests for api/hybrid.py - BM25 + BGE vector fusion (v3.c item 3.4).

Pure-logic tests: weight clamping, min-max, blend arithmetic, fail-soft paths.
No Neo4j, no ONNX - those are exercised by _verify_hybrid.py manually.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from api import hybrid


# ---- weight clamping -------------------------------------------------------


def test_weight_default(monkeypatch):
    monkeypatch.delenv("HYBRID_BM25_WEIGHT", raising=False)
    assert hybrid._weight() == 0.65


def test_weight_clamps_low(monkeypatch):
    monkeypatch.setenv("HYBRID_BM25_WEIGHT", "0.05")
    assert hybrid._weight() == 0.3


def test_weight_clamps_high(monkeypatch):
    monkeypatch.setenv("HYBRID_BM25_WEIGHT", "0.99")
    assert hybrid._weight() == 0.9


def test_weight_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("HYBRID_BM25_WEIGHT", "not-a-number")
    assert hybrid._weight() == 0.65


# ---- min-max ---------------------------------------------------------------


def test_minmax_basic():
    assert hybrid._minmax([0.0, 5.0, 10.0]) == [0.0, 0.5, 1.0]


def test_minmax_flat_returns_half():
    assert hybrid._minmax([3.0, 3.0, 3.0]) == [0.5, 0.5, 0.5]


def test_minmax_empty():
    assert hybrid._minmax([]) == []


# ---- fail-soft -------------------------------------------------------------


def test_fuse_returns_bm25_when_embedder_unavailable():
    bm25 = [{"uid": "IPC_378", "score": 30.0}]
    with patch.object(hybrid.embedder, "is_available", return_value=False):
        merged, used = hybrid.fuse(MagicMock(), "query", bm25)
    assert used is False
    assert merged == bm25


def test_fuse_returns_bm25_when_query_embed_fails():
    bm25 = [{"uid": "IPC_378", "score": 30.0}]
    with patch.object(hybrid.embedder, "is_available", return_value=True), \
         patch.object(hybrid.embedder, "embed_query", return_value=None):
        merged, used = hybrid.fuse(MagicMock(), "query", bm25)
    assert used is False
    assert merged == bm25


def test_fuse_returns_bm25_when_vector_query_raises():
    bm25 = [{"uid": "IPC_378", "score": 30.0}]
    session = MagicMock()
    session.run.side_effect = RuntimeError("index gone")
    with patch.object(hybrid.embedder, "is_available", return_value=True), \
         patch.object(hybrid.embedder, "embed_query", return_value=[0.1] * 384):
        merged, used = hybrid.fuse(session, "query", bm25)
    assert used is False
    assert merged == bm25


# ---- blend arithmetic ------------------------------------------------------


def test_blend_math_is_recomputable(monkeypatch):
    """Principle 3: every hybrid_score must be hand-recomputable from the two raw signals."""
    monkeypatch.setenv("HYBRID_BM25_WEIGHT", "0.7")
    bm25 = [
        {"uid": "A", "score": 10.0},
        {"uid": "B", "score": 30.0},
    ]
    # Vector returns the same two uids with cosines.
    vec_result = [
        {"uid": "A", "cosine": 0.9},
        {"uid": "B", "cosine": 0.5},
    ]
    session = MagicMock()
    session.run.return_value = vec_result

    with patch.object(hybrid.embedder, "is_available", return_value=True), \
         patch.object(hybrid.embedder, "embed_query", return_value=[0.1] * 384), \
         patch.object(hybrid, "_hydrate", return_value={}):
        merged, used = hybrid.fuse(session, "q", bm25)

    assert used is True
    by_uid = {m["uid"]: m for m in merged}
    # BM25 min-max: A=0.0, B=1.0. Cosine min-max: A=1.0, B=0.0.
    # hybrid(A) = 0.7*0.0 + 0.3*1.0 = 0.3
    # hybrid(B) = 0.7*1.0 + 0.3*0.0 = 0.7
    assert by_uid["A"]["hybrid_score"] == pytest.approx(0.3, abs=1e-4)
    assert by_uid["B"]["hybrid_score"] == pytest.approx(0.7, abs=1e-4)
    # Raw signals preserved for audit.
    assert by_uid["A"]["bm25_score"] == 10.0
    assert by_uid["A"]["vector_cosine"] == 0.9


def test_bm25_dominant_at_default_weight(monkeypatch):
    """At 0.65 weight, a strong-BM25/low-cosine row must still beat a weak-BM25/high-cosine row."""
    monkeypatch.delenv("HYBRID_BM25_WEIGHT", raising=False)
    bm25 = [
        {"uid": "STRONG_BM25", "score": 50.0},
        {"uid": "WEAK_BM25", "score": 5.0},
    ]
    vec_result = [
        {"uid": "STRONG_BM25", "cosine": 0.4},
        {"uid": "WEAK_BM25", "cosine": 0.95},
    ]
    session = MagicMock()
    session.run.return_value = vec_result

    with patch.object(hybrid.embedder, "is_available", return_value=True), \
         patch.object(hybrid.embedder, "embed_query", return_value=[0.1] * 384), \
         patch.object(hybrid, "_hydrate", return_value={}):
        merged, _ = hybrid.fuse(session, "q", bm25)

    # STRONG_BM25: 0.65*1.0 + 0.35*0.0 = 0.65
    # WEAK_BM25:   0.65*0.0 + 0.35*1.0 = 0.35
    assert merged[0]["uid"] == "STRONG_BM25"


def test_vector_only_candidate_enters_union():
    """A section found by vector but not BM25 must appear, with bm25_score 0.0."""
    bm25 = [{"uid": "A", "score": 10.0}]
    vec_result = [
        {"uid": "A", "cosine": 0.5},
        {"uid": "VECTOR_ONLY", "cosine": 0.8},
    ]
    session = MagicMock()
    session.run.return_value = vec_result
    hydrated = {"VECTOR_ONLY": {"uid": "VECTOR_ONLY", "code": "IPC", "number": "999", "title": "t"}}

    with patch.object(hybrid.embedder, "is_available", return_value=True), \
         patch.object(hybrid.embedder, "embed_query", return_value=[0.1] * 384), \
         patch.object(hybrid, "_hydrate", return_value=hydrated):
        merged, used = hybrid.fuse(session, "q", bm25)

    assert used is True
    uids = [m["uid"] for m in merged]
    assert "VECTOR_ONLY" in uids
    vo = next(m for m in merged if m["uid"] == "VECTOR_ONLY")
    assert vo["bm25_score"] == 0.0
    assert vo["vector_cosine"] == 0.8


def test_empty_bm25_still_allows_vector():
    """If BM25 found nothing but vector did, return the vector candidates."""
    vec_result = [{"uid": "V1", "cosine": 0.9}]
    session = MagicMock()
    session.run.return_value = vec_result
    hydrated = {"V1": {"uid": "V1", "code": "IPC", "number": "1", "title": "t"}}

    with patch.object(hybrid.embedder, "is_available", return_value=True), \
         patch.object(hybrid.embedder, "embed_query", return_value=[0.1] * 384), \
         patch.object(hybrid, "_hydrate", return_value=hydrated):
        merged, used = hybrid.fuse(session, "q", [])

    assert used is True
    assert len(merged) == 1
    assert merged[0]["uid"] == "V1"
