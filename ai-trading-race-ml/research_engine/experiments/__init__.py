"""Strategies, deterministic baselines, replay runner, manifests, metrics, reports.

Public API:

* :class:`research_engine.experiments.strategy.Strategy` /
  :class:`research_engine.experiments.strategy.StrategyContext`,
  :func:`register_strategy`, :func:`create_strategy`.
* :mod:`research_engine.experiments.baselines` - ``cash``, ``static_ladder``,
  ``quant_duration`` and the common bootstrap allocation.
* :class:`research_engine.experiments.runner.ReplayRunner` (``run``/``resume``).
* :mod:`research_engine.experiments.manifest`, ``metrics``, ``report``, ``parity``.
"""
