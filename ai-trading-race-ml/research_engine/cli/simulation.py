"""``fi-research replay ...`` and ``fi-research parity export``.

Ports are injected through a factory ``module:callable`` returning
``(pricing_port, market_port)``: ``--ports``, else ``$FI_SIMULATION_PORTS``,
else :func:`default_ports`, which loads the real numerical core
(``research_engine.market.store.load_default_market``) and fails
with a clear message when it is not installed yet.

Signing: replay transitions are HMAC-signed with ``$FI_TRANSITION_SIGNING_KEY``
(required; never stored in run artifacts). Parity fixtures use the published
fixture key from :mod:`research_engine.experiments.parity`.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PORTS_ENV = "FI_SIMULATION_PORTS"
KEY_ENV = "FI_TRANSITION_SIGNING_KEY"


class PortsUnavailable(RuntimeError):
    pass


def default_ports():
    """Build the real QuantLib-backed ports, or explain why they are unavailable."""
    try:
        pricing_module = importlib.import_module("research_engine.pricing.port")
        market_module = importlib.import_module("research_engine.market.store")
    except ModuleNotFoundError as exc:
        raise PortsUnavailable(
            "the numerical core (research_engine.pricing.port / research_engine.market.store) "
            f"is not importable yet ({exc.name}); pass --ports module:callable returning "
            "(pricing_port, market_port)"
        ) from exc
    loader = getattr(market_module, "load_default_market", None)
    if callable(loader):
        return loader()
    for module in (pricing_module, market_module):
        builder = getattr(module, "build_default_ports", None)
        if callable(builder):
            return builder()
    try:
        market = market_module.CurveMarketDataPort()
        pricing = pricing_module.QuantLibPricingPort(market)
    except (AttributeError, TypeError) as exc:
        raise PortsUnavailable(
            "could not construct the default ports automatically "
            f"({type(exc).__name__}: {exc}); pass --ports module:callable"
        ) from exc
    return pricing, market


def load_ports(spec: str | None):
    spec = spec or os.environ.get(PORTS_ENV)
    if not spec:
        return default_ports()
    module_name, _, attr = spec.partition(":")
    if not attr:
        raise PortsUnavailable(f"--ports must be module:callable, got {spec!r}")
    try:
        factory = getattr(importlib.import_module(module_name), attr)
    except (ModuleNotFoundError, AttributeError) as exc:
        raise PortsUnavailable(f"cannot load ports factory {spec!r}: {exc}") from exc
    return factory()


def _signing_key() -> bytes:
    key = os.environ.get(KEY_ENV, "")
    if not key:
        raise PortsUnavailable(f"set {KEY_ENV} to sign transition proposals")
    return key.encode("utf-8")


def _load_config(path: Path):
    from research_engine.experiments.runner import ReplayConfig

    return ReplayConfig.model_validate_json(Path(path).read_text())


def _cmd_run(args) -> int:
    from research_engine.experiments.runner import ReplayRunner

    config = _load_config(args.config)
    pricing, market = load_ports(args.ports)
    runner = ReplayRunner(
        config,
        pricing,
        market,
        Path(args.run_dir),
        _signing_key(),
        generated_at=datetime.now(timezone.utc),  # operational metadata only
    )
    result = runner.run()
    print(
        json.dumps(
            {
                "status": result.status,
                "cycles": result.cycles_completed,
                "runDir": str(result.run_dir),
                "failures": result.failures,
            }
        )
    )
    return 0 if result.status == "completed" else 1


def _cmd_resume(args) -> int:
    from research_engine.experiments.runner import ReplayRunner

    run_dir = Path(args.run_dir)
    config = _load_config(run_dir / "config.json")
    pricing, market = load_ports(args.ports)
    result = ReplayRunner(config, pricing, market, run_dir, _signing_key()).resume()
    print(
        json.dumps(
            {
                "status": result.status,
                "cycles": result.cycles_completed,
                "runDir": str(result.run_dir),
                "failures": result.failures,
            }
        )
    )
    return 0 if result.status == "completed" else 1


def _cmd_report(args) -> int:
    from research_engine.experiments.report import write_report

    json_path, md_path = write_report(Path(args.run_dir), Path(args.out) if args.out else None)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}))
    return 0


def _cmd_parity(args) -> int:
    from research_engine.experiments.parity import export_parity_fixture

    pricing, market = load_ports(args.ports)
    config = _load_config(args.config) if args.config else None
    paths = export_parity_fixture(
        pricing, market, Path(args.out) if args.out else None, config=config
    )
    print(json.dumps({k: str(v) for k, v in paths.items()}))
    return 0


def _guard(func):
    def run(args):
        try:
            return func(args)
        except PortsUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3

    return run


def register(subparsers) -> None:
    replay = subparsers.add_parser("replay", help="offline daily replay")
    replay_sub = replay.add_subparsers(dest="replay_command", metavar="<action>")

    run = replay_sub.add_parser("run", help="start a replay from a config file")
    run.add_argument("--config", required=True, type=Path, help="ReplayConfig JSON")
    run.add_argument("--run-dir", required=True, type=Path)
    run.add_argument("--ports", help="ports factory module:callable")
    run.set_defaults(func=_guard(_cmd_run))

    resume = replay_sub.add_parser("resume", help="resume from the last checkpoint")
    resume.add_argument("--run-dir", required=True, type=Path)
    resume.add_argument("--ports", help="ports factory module:callable")
    resume.set_defaults(func=_guard(_cmd_resume))

    report = replay_sub.add_parser("report", help="write report.json and report.md")
    report.add_argument("--run-dir", required=True, type=Path)
    report.add_argument("--out", type=Path)
    report.set_defaults(func=_guard(_cmd_report))

    parity = subparsers.add_parser("parity", help="offline/application parity fixtures")
    parity_sub = parity.add_subparsers(dest="parity_command", metavar="<action>")
    export = parity_sub.add_parser("export", help="export parity fixtures")
    export.add_argument("--out", type=Path, help="default: <repo>/contracts/fixtures/parity")
    export.add_argument("--config", type=Path, help="ReplayConfig JSON (default fixture config)")
    export.add_argument("--ports", help="ports factory module:callable")
    export.set_defaults(func=_guard(_cmd_parity))
