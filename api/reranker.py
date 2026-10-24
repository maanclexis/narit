"""Local cross-encoder reranker — ONNX, no torch.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (ONNX int8 port via Xenova).
Purpose: rescore BM25 top-20 candidates, keep top-5 by cross-encoder logit.

Design contract:
  - Import is free: no disk IO, no ONNX session, no failure modes.
  - Scoring fails soft: on any error, returns None so caller falls back to BM25 order.
  - Score is the raw model logit. Ordering is monotonic, so we don't sigmoid;
    the audit trail shows exactly what the model emitted.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "reranker"
_MODEL_FILE = "model_quantized.onnx"
_TOKENIZER_FILE = "tokenizer.json"
_DEFAULT_MAX_LEN = 256  # 512 in the card; 256 is 2x faster and plenty for short legal pairs

_state_lock = threading.Lock()
_session = None
_tokenizer = None
_input_names: list[str] = []
_load_failed = False
_load_attempted = False


def _resolve_model_dir() -> Path:
    env = os.getenv("RERANKER_MODEL_DIR")
    return Path(env).resolve() if env else _DEFAULT_MODEL_DIR


def _load_once() -> None:
    """Idempotent, thread-safe, fail-soft load. Sets module globals."""
    global _session, _tokenizer, _input_names, _load_failed, _load_attempted

    if _load_attempted:
        return
    with _state_lock:
        if _load_attempted:
            return
        _load_attempted = True

        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except Exception as exc:  # pragma: no cover - env-level failure
            logger.warning("reranker: deps unavailable (%s); BM25 order will be used", exc)
            _load_failed = True
            return

        model_dir = _resolve_model_dir()
        model_path = model_dir / _MODEL_FILE
        tok_path = model_dir / _TOKENIZER_FILE

        if not model_path.is_file() or not tok_path.is_file():
            logger.warning(
                "reranker: model files missing under %s; BM25 order will be used", model_dir
            )
            _load_failed = True
            return

        try:
            so = ort.SessionOptions()
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            so.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2)))
            so.inter_op_num_threads = 1
            _session = ort.InferenceSession(
                str(model_path), sess_options=so, providers=["CPUExecutionProvider"]
            )
            _input_names = [i.name for i in _session.get_inputs()]
            _tokenizer = Tokenizer.from_file(str(tok_path))
            _tokenizer.enable_truncation(max_length=_DEFAULT_MAX_LEN)
            logger.info(
                "reranker: loaded %s (inputs=%s)", model_path.name, _input_names
            )
        except Exception as exc:
            logger.warning("reranker: load failed (%s); BM25 order will be used", exc)
            _session = None
            _tokenizer = None
            _input_names = []
            _load_failed = True


def is_available() -> bool:
    """True iff the ONNX session and tokenizer loaded cleanly."""
    _load_once()
    return _session is not None and _tokenizer is not None


def _score_pairs(pairs: list[tuple[str, str]]) -> list[float] | None:
    """Score (query, passage) pairs. Returns raw logits, one per pair."""
    if not pairs:
        return []
    _load_once()
    if _session is None or _tokenizer is None:
        return None

    try:
        import numpy as np

        queries = [q for q, _ in pairs]
        passages = [p for _, p in pairs]
        encodings = _tokenizer.encode_batch(
            [(q, p) for q, p in zip(queries, passages)]
        )

        max_len = max(len(e.ids) for e in encodings)
        input_ids = np.zeros((len(encodings), max_len), dtype=np.int64)
        attention_mask = np.zeros((len(encodings), max_len), dtype=np.int64)
        for i, enc in enumerate(encodings):
            n = len(enc.ids)
            input_ids[i, :n] = enc.ids
            attention_mask[i, :n] = enc.attention_mask

        feed: dict[str, "np.ndarray"] = {}
        for name in _input_names:
            if name == "input_ids":
                feed[name] = input_ids
            elif name == "attention_mask":
                feed[name] = attention_mask
            elif name == "token_type_ids":
                feed[name] = np.zeros_like(input_ids)
            else:
                logger.warning("reranker: unexpected model input %r; aborting score", name)
                return None

        outputs = _session.run(None, feed)
        logits = np.asarray(outputs[0]).reshape(-1)
        return [float(x) for x in logits]
    except Exception as exc:  # pragma: no cover - runtime failure
        logger.warning("reranker: scoring failed (%s); BM25 order will be used", exc)
        return None


def _minmax(vals: list[float]) -> list[float]:
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    span = hi - lo
    if span <= 0:
        return [0.5] * len(vals)
    return [(v - lo) / span for v in vals]


def rerank(
    query: str,
    candidates: list[dict],
    text_key: str = "text",
    title_key: str = "title",
    top_k: int = 5,
    bm25_key: str = "score",
    bm25_weight: float = 0.7,
    score_label: str = "bm25_score",
) -> tuple[list[dict], bool]:
    """Rescore candidates by cross-encoder, blended with caller's BM25 score.

    Combined score: bm25_weight * norm(bm25) + (1 - bm25_weight) * norm(reranker_logit).
    BM25 carries the domain signal; cross-encoder nudges ordering within close
    BM25 tiers. Both raw scores are preserved on each candidate — the retrieval
    signal lands under `score_label` (default 'bm25_score'; 'hybrid_score' when
    the caller pre-fused a vector channel) and 'reranker_score'; combined lands
    in 'final_score'.

    Returns (reranked_list, used_reranker).
    On failure or empty input, returns (candidates[:top_k], False) so caller sees BM25 order.
    """
    if not candidates:
        return [], False

    # ms-marco was trained on short web passages, not 800-word statute blocks.
    # Title + first 300 chars of text keeps the pair inside its training distribution.
    passages: list[str] = []
    for c in candidates:
        title = str(c.get(title_key) or "").strip()
        text = str(c.get(text_key) or "").strip()
        passages.append((title + "\n" + text[:300])[:500].strip())

    scores = _score_pairs(list(zip([query] * len(passages), passages)))
    if scores is None:
        return candidates[:top_k], False

    raw_bm25 = [float(c.get(bm25_key) or 0.0) for c in candidates]
    norm_bm25 = _minmax(raw_bm25)
    norm_rer = _minmax([float(s) for s in scores])

    w_bm25 = max(0.0, min(1.0, bm25_weight))
    w_rer = 1.0 - w_bm25

    for cand, b_raw, r_raw, b_n, r_n in zip(candidates, raw_bm25, scores, norm_bm25, norm_rer):
        cand[score_label] = round(float(b_raw), 4)
        cand["reranker_score"] = round(float(r_raw), 4)
        cand["final_score"] = round(w_bm25 * b_n + w_rer * r_n, 4)

    ranked = sorted(candidates, key=lambda c: c.get("final_score", float("-inf")), reverse=True)
    return ranked[:top_k], True
