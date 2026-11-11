"""Export JSON schemas and canonical-JSON test vectors for cross-runtime tests.

Usage: ``python -m research_engine.contracts.export [repo_root]``
Writes ``contracts/schemas/v1/*.schema.json`` and
``contracts/test-vectors/canonical-json.json`` at the repository root.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from . import decisions, portfolio
from .common import canonical_json, content_hash, sign_hash

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "portfolio-state": portfolio.PortfolioState,
    "transition-request": portfolio.TransitionRequest,
    "transition-proposal": portfolio.TransitionProposal,
    "risk-policy": portfolio.RiskPolicy,
    "execution-model": portfolio.ExecutionModel,
    "valuation-snapshot": portfolio.ValuationSnapshot,
    "decision-request": decisions.DecisionRequest,
    "strategy-result": decisions.StrategyResult,
}

TEST_SIGNING_KEY = b"test-vector-signing-key"


def _vectors() -> list[dict]:
    samples = [
        {"b": 1, "a": "x"},
        {"nested": {"z": [3, 2, 1], "a": None, "t": True, "f": False}},
        {"unicode": "café – 東京 \U0001f4c8", "quote": 'say "hi"\\'},
        {"control": "line1\nline2\ttab\r\x01\x1f\x7f", "slash": "a/b<c>&"},
        {"money": "1234.56", "neg": "-0.01", "face": "1000000", "weight": "0.30"},
        {"emptyObj": {}, "emptyArr": [], "zero": 0, "negInt": -42},
        {"Zeta": 1, "alpha": 2, "Alpha": 3, "_under": 4, "1num": 5},
    ]
    out = []
    for sample in samples:
        text = canonical_json(sample)
        digest = content_hash(sample)
        out.append(
            {
                "input": sample,
                "canonical": text,
                "sha256": digest,
                "signature": sign_hash(digest, TEST_SIGNING_KEY),
            }
        )
    return out


def export(repo_root: Path) -> None:
    schema_dir = repo_root / "contracts" / "schemas" / "v1"
    schema_dir.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMA_MODELS.items():
        schema = TypeAdapter(model).json_schema(by_alias=True, mode="serialization")
        (schema_dir / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n"
        )
    vectors_dir = repo_root / "contracts" / "test-vectors"
    vectors_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "description": "Canonical JSON vectors: sorted keys (code point order), compact "
        "separators, ASCII escaping, lowercase \\u escapes, no floats.",
        "signingKeyUtf8": TEST_SIGNING_KEY.decode(),
        "vectors": _vectors(),
    }
    (vectors_dir / "canonical-json.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )
    assert Decimal("1")  # keep import for type checkers


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
    export(root)
    print(f"exported schemas and vectors under {root / 'contracts'}")
