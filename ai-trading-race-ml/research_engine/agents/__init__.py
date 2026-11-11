"""AI strategies, bounded specialist team, typed tools, budgets and validation (M3, M6).

Importing this package registers ``llm_market``, ``llm_rag``, ``llm_graph`` and
``llm_team`` with the experiment strategy registry. Public entry points:

* :func:`create_llm_strategy` / :func:`build_llm_strategies` - strategies with an
  injected provider (``build_provider("reference" | "recorded" | "anthropic" |
  "openai", ...)``) and evidence port;
* :func:`research_note` - cited research note, no order authority;
* :mod:`research_engine.agents.recording` - capture and replay recorded responses.
"""

from __future__ import annotations

from .budget import BudgetExceeded, BudgetLedger, PriceSchedule, TaskAllowance
from .ports import EvidencePort, RetrievalEvidencePort, open_default_evidence_port
from .providers import build_provider
from .research_note import ResearchNoteResult, research_note
from .result import seal_result, verify_result
from .strategies import (
    LLM_STRATEGY_IDS,
    LlmStrategy,
    build_llm_strategies,
    create_llm_strategy,
)

__all__ = [
    "BudgetExceeded",
    "BudgetLedger",
    "EvidencePort",
    "LLM_STRATEGY_IDS",
    "LlmStrategy",
    "PriceSchedule",
    "RetrievalEvidencePort",
    "TaskAllowance",
    "build_llm_strategies",
    "build_provider",
    "create_llm_strategy",
    "open_default_evidence_port",
    "ResearchNoteResult",
    "research_note",
    "seal_result",
    "verify_result",
]
