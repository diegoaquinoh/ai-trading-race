"""Strategy construction for the decision endpoint.

* Deterministic baselines (``cash``, ``static_ladder``, ``quant_duration``) come
  from the research-engine registry
  (``research_engine.experiments.strategy.create_strategy``).
* Agent strategies (``llm_market``, ``llm_rag``, ``llm_graph``, ``llm_team``) are
  built with ``research_engine.agents.create_llm_strategy`` and *injected*
  dependencies: the configured provider, an evidence port over the engine's
  already loaded READY index, the shared calculation store and the shared
  signing key. Registry construction is never used for them in the API because
  it would open (ingest/build) a default evidence index inside a request.

The model provider is chosen by configuration only
(``ML_SERVICE_STRATEGY_PROVIDER`` = reference | recorded | anthropic | openai,
``ML_SERVICE_STRATEGY_MODEL``, ``ML_SERVICE_RECORDED_RESPONSES_DIR``,
``ML_SERVICE_STRATEGY_BASE_URL``); no request field can select a provider, a
model or a risk policy. Provider clients read credentials from their own
environment variables (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``); only whether
one is present is reported.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

from app.config import Settings
from research_engine.contracts.decisions import RetrievalMode, StrategyKind

log = logging.getLogger(__name__)

PROVIDERS = ("reference", "recorded", "anthropic", "openai")
NON_DETERMINISTIC_KINDS = (StrategyKind.SINGLE_AGENT, StrategyKind.SPECIALIST_TEAM)
CREDENTIAL_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


class ProviderUnavailable(RuntimeError):
    pass


def _agents():
    """``research_engine.agents`` (registers the LLM strategies) or None."""
    try:
        import research_engine.agents as agents
    except Exception as exc:  # a broken agents package must not break the baselines
        log.warning("agent strategies unavailable: %s", exc)
        return None
    return agents


def llm_strategy_spec(strategy_id: str) -> Optional[tuple[str, RetrievalMode, bool]]:
    """``(version, retrieval mode, team)`` for an agent strategy id, else None."""
    if not strategy_id.startswith("llm_"):
        return None
    if _agents() is None:
        return None
    try:
        from research_engine.agents.strategies import STRATEGY_VERSIONS
    except ImportError:
        return None
    return STRATEGY_VERSIONS.get(strategy_id)


class StrategyService:
    def __init__(self, settings: Settings):
        self.provider_name = settings.strategy_provider
        if self.provider_name not in PROVIDERS:
            raise ValueError(f"unsupported strategy provider {self.provider_name!r}")
        self.model = settings.strategy_model
        self.base_url = settings.strategy_base_url
        self.recorded_dir = settings.recorded_responses_dir
        self._provider: Any = None
        self._provider_error: Optional[str] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Registry
    # ------------------------------------------------------------------ #
    def registered_ids(self) -> list[str]:
        from research_engine.experiments import baselines  # noqa: F401  (registers)
        from research_engine.experiments.strategy import STRATEGY_REGISTRY

        _agents()
        return sorted(STRATEGY_REGISTRY)

    def create(
        self,
        strategy_id: str,
        *,
        provider: Any = None,
        evidence: Any = None,
        calc_store: Any = None,
        signing_key: Optional[bytes] = None,
    ) -> Any:
        """Build a strategy; agent strategies get injected dependencies only."""
        spec = llm_strategy_spec(strategy_id)
        if spec is not None:
            from research_engine.agents import create_llm_strategy

            if provider is None:
                provider = self.provider()
            return create_llm_strategy(
                strategy_id,
                None,
                provider=provider,
                evidence=evidence,
                calc_store=calc_store,
                signing_key=signing_key,
            )
        from research_engine.experiments.strategy import create_strategy

        if strategy_id.startswith("llm_"):
            raise KeyError(f"agent strategy {strategy_id!r} is not available")
        self.registered_ids()
        return create_strategy(strategy_id)

    def describe_strategies(self) -> list[dict[str, Any]]:
        out = []
        for sid in self.registered_ids():
            spec = llm_strategy_spec(sid)
            if spec is not None:
                version, mode, team = spec
                out.append(
                    {
                        "strategyId": sid,
                        "available": True,
                        "version": version,
                        "kind": (
                            StrategyKind.SPECIALIST_TEAM if team else StrategyKind.SINGLE_AGENT
                        ).value,
                        "invested": True,
                        "deterministic": self.provider_name in ("reference", "recorded"),
                        "usesModelProvider": True,
                        "retrievalMode": mode.value,
                        "requiresEvidence": mode != RetrievalMode.NONE,
                    }
                )
                continue
            try:
                strategy = self.create(sid)
            except Exception as exc:
                out.append({"strategyId": sid, "available": False, "error": type(exc).__name__})
                continue
            kind = getattr(strategy, "kind", None)
            out.append(
                {
                    "strategyId": sid,
                    "available": True,
                    "version": (getattr(strategy, "config", None) or {}).get("version"),
                    "kind": kind.value if kind is not None else None,
                    "invested": bool(getattr(strategy, "invested", False)),
                    "deterministic": bool(getattr(strategy, "deterministic", False)),
                    "usesModelProvider": False,
                    "retrievalMode": RetrievalMode.NONE.value,
                    "requiresEvidence": False,
                }
            )
        return out

    # ------------------------------------------------------------------ #
    # Provider (configuration only)
    # ------------------------------------------------------------------ #
    def credential_configured(self) -> Optional[bool]:
        env = CREDENTIAL_ENV.get(self.provider_name)
        return bool(os.environ.get(env)) if env else None

    def compatible_modes(self) -> list[str]:
        return {
            "reference": ["recorded_replay", "fresh_inference"],
            "recorded": ["recorded_replay"],
            "anthropic": ["fresh_inference"],
            "openai": ["fresh_inference"],
        }[self.provider_name]

    def describe(self) -> dict[str, Any]:
        model = self.model or None
        if self._provider is not None:
            model = getattr(self._provider, "model", model)
        elif self.provider_name == "reference":
            try:
                from research_engine.agents.providers import REFERENCE_MODEL_ID

                model = REFERENCE_MODEL_ID
            except Exception:
                pass
        return {
            "configured": self.provider_name,
            "model": model,
            "baseUrlConfigured": bool(self.base_url),
            "recordedResponsesConfigured": bool(self.recorded_dir),
            "credentialConfigured": self.credential_configured(),
            "responseModes": self.compatible_modes(),
            "error": self._provider_error,
        }

    def provider(self) -> Any:
        """Build (once) the configured provider; raises :class:`ProviderUnavailable`."""
        with self._lock:
            if self._provider is not None:
                return self._provider
            try:
                self._provider = self._build_provider()
                self._provider_error = None
            except Exception as exc:
                self._provider_error = f"{type(exc).__name__}: {exc}"
                raise ProviderUnavailable(self._provider_error) from exc
            return self._provider

    def _build_provider(self) -> Any:
        from research_engine.agents.providers import build_provider

        name = self.provider_name
        if name == "recorded" and not self.recorded_dir:
            raise ProviderUnavailable("ML_SERVICE_RECORDED_RESPONSES_DIR is not set")
        if name == "openai" and not self.model:
            raise ProviderUnavailable("ML_SERVICE_STRATEGY_MODEL is required for openai")
        kwargs: dict[str, Any] = {}
        if self.model and name != "reference":
            kwargs["model"] = self.model
        if self.recorded_dir and name == "recorded":
            kwargs["recordings"] = self.recorded_dir
        if self.base_url and name in ("anthropic", "openai"):
            kwargs["base_url"] = self.base_url
        if name == "openai":
            kwargs["provider_label"] = "openai"
        return build_provider(name, **kwargs)
