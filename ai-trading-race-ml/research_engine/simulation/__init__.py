"""Canonical simulation/accounting engine (workstream C, milestone M2).

Public API:

* :func:`research_engine.simulation.engine.propose_transition` - pure, signed
  transition proposals for every ``CommandType``.
* :class:`research_engine.simulation.store.OfflineStateStore` - offline commit
  path mirroring the .NET checks (versions, idempotency, signatures, balance).
* :mod:`research_engine.simulation.ports` - ``PricingPort``/``MarketDataPort``.

Submodules are imported lazily by callers to keep ``ports`` import-light.
"""
