"""Embedding providers (spec 11.3, 12.3).

``hash-embed-v1`` is the pinned deterministic local baseline: signed feature
hashing (BLAKE2b, 1,024 buckets) of the *set* of ``lex-norm-v1`` unigrams and
adjacent bigrams. Vectors are integers, so dot products are exact and rankings
are bit-for-bit reproducible on any machine.

Honest label: this is a **lexical-semantic baseline, not a neural embedding
model**. It captures term and phrase overlap (including bigrams), not synonymy
or paraphrase. A real provider can be plugged in through ``EmbeddingProvider``;
the provider id, model and dimensions are recorded in every ``IndexBuild``, and a
change creates a new build.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from research_engine.evidence.textnorm import lexical_terms


class EmbeddingProvider(Protocol):
    provider_id: str
    model: str
    dimensions: int
    exact_integer: bool

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashEmbeddingProvider:
    provider_id = "local-hash"
    model = "hash-embed-v1"
    exact_integer = True

    def __init__(self, dimensions: int = 1024):
        self.dimensions = dimensions

    def _features(self, text: str) -> set[str]:
        terms = lexical_terms(text)
        feats = set(terms)
        feats.update(f"{a} {b}" for a, b in zip(terms, terms[1:]))
        return feats

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dimensions), dtype=np.int64)
        for row, text in enumerate(texts):
            for feature in sorted(self._features(text)):
                digest = hashlib.blake2b(
                    feature.encode("utf-8"), digest_size=8, person=b"hashemb1"
                ).digest()
                value = int.from_bytes(digest, "big")
                index = value % self.dimensions
                out[row, index] += 1 if (value >> 40) & 1 else -1
        return out


def cosine_scores(matrix: np.ndarray, query: np.ndarray) -> np.ndarray:
    """Exact cosine similarity of each row with ``query`` (zero vectors score 0)."""
    if matrix.dtype.kind == "i" and query.dtype.kind == "i":
        dots = (matrix @ query).astype(np.float64)
        norms = np.sqrt((matrix * matrix).sum(axis=1).astype(np.float64))
        qnorm = float(np.sqrt(float(int((query * query).sum()))))
    else:
        dots = matrix.astype(np.float64) @ query.astype(np.float64)
        norms = np.sqrt((matrix.astype(np.float64) ** 2).sum(axis=1))
        qnorm = float(np.sqrt((query.astype(np.float64) ** 2).sum()))
    denom = norms * qnorm
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = np.where(denom > 0, dots / np.where(denom > 0, denom, 1.0), 0.0)
    return scores
