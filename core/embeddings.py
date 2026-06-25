"""Local, on-device embeddings for the Brain (semantic search + dedup).

Uses `fastembed` (ONNX, no PyTorch) when available — clean on Windows. Degrades
gracefully to a no-op when the library/model isn't present, so the Brain keeps
working with keyword search only (semantic features simply switch off).

Vectors are stored as raw float32 bytes (BLOB) on each brain_memories row.
Retrieval/dedup is brute-force cosine in NumPy — plenty fast at personal scale.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384-dim, small + good
EMBED_DIM = 384

_model = None            # lazy-loaded fastembed model
_unavailable = False     # set True once we know it can't load (don't retry forever)

try:  # numpy is a hard-ish dep, but degrade if missing too
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    np = None  # type: ignore
    _HAS_NUMPY = False


def _get_model():
    global _model, _unavailable
    if _model is not None:
        return _model
    if _unavailable or not _HAS_NUMPY:
        return None
    try:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=MODEL_NAME)
        logger.info("Brain embeddings ready: %s", MODEL_NAME)
        return _model
    except Exception as e:  # library or model download missing
        logger.warning("Brain embeddings unavailable (%s) — falling back to keyword search.", e)
        _unavailable = True
        return None


def is_available() -> bool:
    return _get_model() is not None


def embed_one(text: str) -> Optional["np.ndarray"]:
    """Return a unit-normalized float32 vector, or None if embeddings are off."""
    vecs = embed([text])
    return vecs[0] if vecs else None


def embed(texts: list[str]) -> list["np.ndarray"]:
    model = _get_model()
    if model is None or not texts:
        return []
    try:
        out = list(model.embed(texts))
        vecs = []
        for v in out:
            arr = np.asarray(v, dtype="float32")
            n = float(np.linalg.norm(arr))
            if n > 0:
                arr = arr / n
            vecs.append(arr)
        return vecs
    except Exception as e:  # pragma: no cover
        logger.warning("embed() failed: %s", e)
        return []


def to_blob(vec: Optional["np.ndarray"]) -> Optional[bytes]:
    if vec is None or not _HAS_NUMPY:
        return None
    return np.asarray(vec, dtype="float32").tobytes()


def from_blob(blob: Optional[bytes]) -> Optional["np.ndarray"]:
    if not blob or not _HAS_NUMPY:
        return None
    return np.frombuffer(blob, dtype="float32")


def cosine(a: Optional["np.ndarray"], b: Optional["np.ndarray"]) -> float:
    if a is None or b is None or not _HAS_NUMPY:
        return 0.0
    if a.shape != b.shape:
        return 0.0
    # vectors are already normalized in embed(); guard anyway
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def cosine_topk(query: Optional["np.ndarray"],
                candidates: list[tuple[int, Optional["np.ndarray"]]],
                k: int = 8, min_score: float = 0.0) -> list[tuple[int, float]]:
    """candidates = [(id, vec)] → [(id, score)] sorted desc, filtered by min_score."""
    if query is None or not candidates or not _HAS_NUMPY:
        return []
    scored = []
    for cid, vec in candidates:
        if vec is None:
            continue
        s = cosine(query, vec)
        if s >= min_score:
            scored.append((cid, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
