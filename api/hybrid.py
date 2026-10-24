"""Hybrid retrieval - BM25 fulltext + BGE vector cosine (v3.c item 3.4).

Query-time half. Index-time embeddings are written by scripts/build_embeddings.py.

Fusion contract (auditable per principle 3):
  - Two independent channels: BM25 (existing _CYPHER top-N) and vector cosine
    (db.index.vector.queryNodes on sectionEmbedding).
  - Union by uid. Each row carries bm25_score (0.0 if absent) and
    vector_cosine (0.0 if absent).
  - Each signal min-max normalized ACROSS THE UNION, then blended:
        hybrid_score = w * norm(bm25) + (1 - w) * norm(cosine)
    with w = HYBRID_BM25_WEIGHT (default 0.65, clamped [0.3, 0.9]).
  - BM25 stays dominant: same lesson as the 3.3 reranker, vector nudges paraphrase
    recall and never overrides exact statutory term matches on its own.
  - Both raw signals and the blended score land on every row; a lawyer can
    recompute the arithmetic by hand.

Fails soft: if the embedder or vector index is unavailable, returns the BM25
records unchanged with used_vector=False so analyze.py proceeds BM25-only.
"""

from __future__ import annotations

import logging
import os

from api import embedder

logger = logging.getLogger(__name__)

INDEX_NAME = "sectionEmbedding"
_DEFAULT_WEIGHT = 0.65
_DEFAULT_TOPN = 20


def _weight() -> float:
    try:
        w = float(os.getenv("HYBRID_BM25_WEIGHT", _DEFAULT_WEIGHT))
    except ValueError:
        w = _DEFAULT_WEIGHT
    return max(0.3, min(0.9, w))


def _minmax(vals: list[float]) -> list[float]:
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    span = hi - lo
    if span <= 0:
        return [0.5] * len(vals)
    return [(v - lo) / span for v in vals]


def _hydrate(session, uids: list[str]) -> dict[str, dict]:
    """Fetch the same record shape as _CYPHER for vector-only candidates."""
    if not uids:
        return {}
    result = session.run(
        """
        UNWIND $uids AS u
        MATCH (s:Section {uid: u})
        OPTIONAL MATCH (s)-[:MAPS_TO]->(forward_target:Section)
        OPTIONAL MATCH (backward_source:Section)-[:MAPS_TO]->(s)
        WITH s, COALESCE(backward_source, s) AS primary_sec,
             CASE WHEN backward_source IS NOT NULL THEN s ELSE forward_target END AS mapped_bns
        OPTIONAL MATCH (c:Case)-[:INTERPRETS]->(cs:Section)
        WHERE cs = primary_sec OR cs = mapped_bns
        RETURN primary_sec.code AS code,
               primary_sec.number AS number,
               primary_sec.uid AS uid,
               primary_sec.title AS title,
               primary_sec.text AS text,
               mapped_bns.code AS bns_code,
               mapped_bns.number AS bns_number,
               mapped_bns.title AS bns_title,
               mapped_bns.text AS bns_text,
               collect(DISTINCT {citation: c.citation, title: c.title, summary: c.summary}) AS cases,
               null AS reasoning_step,
               0.0 AS score
        """,
        uids=uids,
    )
    out: dict[str, dict] = {}
    for rec in result:
        d = rec.data()
        if d.get("uid"):
            out[d["uid"]] = d
    return out


def fuse(
    session,
    query: str,
    bm25_records: list[dict],
    top_n: int = _DEFAULT_TOPN,
) -> tuple[list[dict], bool]:
    """Merge BM25 records with vector top-N, blend, return (merged, used_vector).

    bm25_records: rows from _CYPHER, each with 'uid' and 'score'.
    Returns merged list sorted by hybrid_score desc, capped at top_n.
    On any failure, returns (bm25_records, False).
    """
    if not embedder.is_available():
        return bm25_records, False

    qvec = embedder.embed_query(query)
    if qvec is None:
        return bm25_records, False

    try:
        vec_rows = list(
            session.run(
                f"CALL db.index.vector.queryNodes('{INDEX_NAME}', $k, $qvec) "
                "YIELD node, score "
                "RETURN node.uid AS uid, score AS cosine",
                k=top_n,
                qvec=qvec,
            )
        )
    except Exception as exc:
        logger.warning("hybrid: vector query failed (%s); BM25-only", exc)
        return bm25_records, False

    if not vec_rows:
        return bm25_records, False

    cosine_by_uid: dict[str, float] = {}
    for r in vec_rows:
        uid = r["uid"]
        if uid:
            cosine_by_uid[uid] = max(0.0, float(r["cosine"]))

    bm25_by_uid: dict[str, dict] = {}
    for rec in bm25_records:
        uid = rec.get("uid")
        if uid:
            bm25_by_uid[uid] = rec

    # Hydrate vector candidates the BM25 channel did not surface.
    missing = [u for u in cosine_by_uid if u not in bm25_by_uid]
    hydrated = _hydrate(session, missing) if missing else {}

    union: list[dict] = []
    for uid, rec in bm25_by_uid.items():
        row = dict(rec)
        row["bm25_score"] = round(float(rec.get("score") or 0.0), 4)
        row["vector_cosine"] = round(float(cosine_by_uid.get(uid, 0.0)), 4)
        union.append(row)
    for uid in missing:
        rec = hydrated.get(uid)
        if rec is None:
            continue
        row = dict(rec)
        row["bm25_score"] = 0.0
        row["vector_cosine"] = round(float(cosine_by_uid.get(uid, 0.0)), 4)
        union.append(row)

    if not union:
        return bm25_records, False

    raw_bm25 = [float(r.get("bm25_score") or 0.0) for r in union]
    raw_cos = [float(r.get("vector_cosine") or 0.0) for r in union]
    n_bm25 = _minmax(raw_bm25)
    n_cos = _minmax(raw_cos)

    w = _weight()
    v = 1.0 - w
    for row, b_n, c_n in zip(union, n_bm25, n_cos):
        row["hybrid_score"] = round(w * b_n + v * c_n, 4)

    union.sort(key=lambda r: r.get("hybrid_score", float("-inf")), reverse=True)
    return union[:top_n], True
