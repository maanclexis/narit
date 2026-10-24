"""Local BGE-small-en-v1.5 embedder - ONNX, no torch.

Model: Xenova/bge-small-en-v1.5 (ONNX int8 port). 384-dim, CLS pooling, L2 normalized.
Purpose: embed Section title+text at index time and the query at request time,
         for the hybrid BM25 + cosine retrieval channel (v3.c item 3.4).

Design contract (mirrors api/reranker.py):
  - Import is free: no disk IO, no ONNX session, no failure modes.
  - Embedding fails soft: on any error, returns None so caller falls back to BM25-only.
  - Vectors are L2-normalized so cosine == dot product, auditable by hand.

BGE convention: queries get a short retrieval instruction prefix; passages do not.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "embedder"
_MODEL_FILE = "model_quantized.onnx"
_TOKENIZER_FILE = "tokenizer.json"
_DEFAULT_MAX_LEN = 512
EMBED_DIM = 384

# bge-small-en-v1.5 retrieval instruction (query side only, per model card).
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_state_lock = threading.Lock()
_session = None
_tokenizer = None
_input_names: list[str] = []
_output_names: list[str] = []
_load_failed = False
_load_attempted = False


def _resolve_model_dir() -> Path:
    env = os.getenv("EMBEDDER_MODEL_DIR")
    return Path(env).resolve() if env else _DEFAULT_MODEL_DIR


def _load_once() -> None:
    """Idempotent, thread-safe, fail-soft load. Sets module globals."""
    global _session, _tokenizer, _input_names, _output_names, _load_failed, _load_attempted

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
            logger.warning("embedder: deps unavailable (%s); BM25-only will be used", exc)
            _load_failed = True
            return

        model_dir = _resolve_model_dir()
        model_path = model_dir / _MODEL_FILE
        tok_path = model_dir / _TOKENIZER_FILE

        if not model_path.is_file() or not tok_path.is_file():
            logger.warning(
                "embedder: model files missing under %s; BM25-only will be used", model_dir
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
            _output_names = [o.name for o in _session.get_outputs()]
            _tokenizer = Tokenizer.from_file(str(tok_path))
            _tokenizer.enable_truncation(max_length=_DEFAULT_MAX_LEN)
            logger.info("embedder: loaded %s (inputs=%s)", model_path.name, _input_names)
        except Exception as exc:
            logger.warning("embedder: load failed (%s); BM25-only will be used", exc)
            _session = None
            _tokenizer = None
            _input_names = []
            _output_names = []
            _load_failed = True


def is_available() -> bool:
    """True iff the ONNX session and tokenizer loaded cleanly."""
    _load_once()
    return _session is not None and _tokenizer is not None


def _embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed a batch of strings. CLS pooling + L2 normalize. Returns list of 384-float vectors."""
    if not texts:
        return []
    _load_once()
    if _session is None or _tokenizer is None:
        return None

    try:
        import numpy as np

        encodings = _tokenizer.encode_batch(texts)
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
                logger.warning("embedder: unexpected model input %r; aborting embed", name)
                return None

        outputs = _session.run(None, feed)
        # BGE / sentence-transformers convention: sentence embedding = CLS token (position 0).
        hidden = np.asarray(outputs[0])
        cls = hidden[:, 0, :].astype(np.float32)
        # L2 normalize so cosine similarity == dot product.
        norms = np.linalg.norm(cls, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = cls / norms
        return [[float(x) for x in row] for row in vecs]
    except Exception as exc:  # pragma: no cover - runtime failure
        logger.warning("embedder: embedding failed (%s); BM25-only will be used", exc)
        return None


def embed_passages(texts: list[str]) -> list[list[float]] | None:
    """Embed passages (index-time Section title+text). No query prefix."""
    return _embed_texts(texts)


def embed_query(query: str) -> list[float] | None:
    """Embed a single query with the BGE retrieval instruction prefix."""
    if not query:
        return None
    vecs = _embed_texts([_QUERY_PREFIX + query])
    if vecs is None or not vecs:
        return None
    return vecs[0]
