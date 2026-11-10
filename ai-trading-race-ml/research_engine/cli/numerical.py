"""Numerical-core CLI commands (``fi-research ...``).

* ``curve build --date D``                       curve snapshot for a session
* ``price --security S --date D [--settlement]`` settlement-anchored price
* ``risk --security S --date D [--face F]``      position risk (DV01, key rates, durations)
* ``scenario --security S --date D --scenario X`` full-repricing scenario
* ``instruments list [--date D]``                synthetic universe
* ``market admission [--start --end]``           dataset release gate report
* ``market fetch-treasury --year Y``             network: download + store raw CSV

All commands except ``market fetch-treasury`` run offline from fixtures and
print JSON (camelCase, decimal strings) to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from typing import Any

from research_engine.contracts.common import ContractModel


def _date(text: str) -> date:
    return date.fromisoformat(text)


def _emit(payload: Any) -> None:
    if isinstance(payload, ContractModel):
        payload = payload.to_wire()
    json.dump(payload, sys.stdout, indent=2, sort_keys=False, default=str)
    sys.stdout.write("\n")


def _ports():
    from research_engine.market.store import load_default_market

    return load_default_market()


def _session_curve(market, day: date):
    info = market.curve_for_session(day)
    if info is None:
        raise SystemExit(f"no curve observation for session {day} ({market.session_status(day)})")
    if info.status != "READY":
        snap = market.curve_snapshot_for_session(day)
        raise SystemExit(f"curve for {day} is {info.status}: {snap.failure_reasons}")
    return info


def cmd_curve_build(args: argparse.Namespace) -> int:
    _, market = _ports()
    snap = market.curve_snapshot_for_session(args.date)
    if snap is None:
        raise SystemExit(f"no observation for {args.date} ({market.session_status(args.date)})")
    _emit(snap)
    return 0 if snap.status.value == "READY" else 1


def cmd_price(args: argparse.Namespace) -> int:
    pricing, market = _ports()
    info = _session_curve(market, args.date)
    settlement = args.settlement or pricing.settlement_date(args.security, args.date)
    result = pricing.price(args.security, info.curve_snapshot_id, settlement)
    calc = pricing.calc_store.get(result.calculation_id)
    _emit({"price": result.to_wire(), "calculation": calc.to_wire() if calc else None})
    return 0


def cmd_risk(args: argparse.Namespace) -> int:
    pricing, market = _ports()
    info = _session_curve(market, args.date)
    _emit(pricing.position_risk(args.security, info.curve_snapshot_id, args.date, args.face))
    return 0


def cmd_scenario(args: argparse.Namespace) -> int:
    pricing, market = _ports()
    info = _session_curve(market, args.date)
    _emit(
        pricing.scenario(args.security, info.curve_snapshot_id, args.date, args.scenario, args.face)
    )
    return 0


def cmd_instruments_list(args: argparse.Namespace) -> int:
    pricing, _ = _ports()
    if args.date:
        _emit([i.to_wire() for i in pricing.universe(args.date)])
    else:
        from research_engine.instruments.universe import load_universe

        _emit(load_universe())
    return 0


def cmd_market_admission(args: argparse.Namespace) -> int:
    from research_engine.market.admission import build_dataset_admission_report
    from research_engine.market.treasury import default_treasury_dataset

    _, market = _ports()
    report = build_dataset_admission_report(
        default_treasury_dataset(), args.start, args.end, market=market
    )
    _emit(report)
    return 0 if report.eligible_for_benchmark else 1


def cmd_market_fetch_treasury(args: argparse.Namespace) -> int:
    from research_engine.market.treasury import fetch_treasury_year, store_raw_artifact

    raw = fetch_treasury_year(args.year)
    artifact = store_raw_artifact(args.year, raw, allow_revision=args.allow_revision)
    _emit(artifact)
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    curve = subparsers.add_parser("curve", help="curve snapshots")
    curve_sub = curve.add_subparsers(dest="curve_command", metavar="<curve-command>")
    build = curve_sub.add_parser("build", help="build/show the curve snapshot for a session")
    build.add_argument("--date", type=_date, required=True)
    build.set_defaults(func=cmd_curve_build)

    price = subparsers.add_parser("price", help="settlement-anchored model price")
    price.add_argument("--security", required=True)
    price.add_argument("--date", type=_date, required=True, help="session/trade date")
    price.add_argument("--settlement", type=_date, default=None, help="default: T+1")
    price.set_defaults(func=cmd_price)

    risk = subparsers.add_parser("risk", help="position risk at a session")
    risk.add_argument("--security", required=True)
    risk.add_argument("--date", type=_date, required=True)
    risk.add_argument("--face", type=Decimal, default=Decimal("1000000"))
    risk.set_defaults(func=cmd_risk)

    scen = subparsers.add_parser("scenario", help="full-repricing scenario (scenario_library_v1)")
    scen.add_argument("--security", required=True)
    scen.add_argument("--date", type=_date, required=True)
    scen.add_argument("--scenario", required=True)
    scen.add_argument("--face", type=Decimal, default=Decimal("1000000"))
    scen.set_defaults(func=cmd_scenario)

    inst = subparsers.add_parser("instruments", help="instrument universe")
    inst_sub = inst.add_subparsers(dest="instruments_command", metavar="<instruments-command>")
    lst = inst_sub.add_parser("list", help="list instruments (outstanding at --date if given)")
    lst.add_argument("--date", type=_date, default=None)
    lst.set_defaults(func=cmd_instruments_list)

    market = subparsers.add_parser("market", help="market data and dataset admission")
    market_sub = market.add_subparsers(dest="market_command", metavar="<market-command>")
    adm = market_sub.add_parser("admission", help="dataset release-gate report")
    adm.add_argument("--start", type=_date, default=date(2023, 1, 1))
    adm.add_argument("--end", type=_date, default=date(2024, 12, 31))
    adm.set_defaults(func=cmd_market_admission)
    fetch = market_sub.add_parser("fetch-treasury", help="NETWORK: download one year's CSV")
    fetch.add_argument("--year", type=int, required=True)
    fetch.add_argument("--allow-revision", action="store_true")
    fetch.set_defaults(func=cmd_market_fetch_treasury)
