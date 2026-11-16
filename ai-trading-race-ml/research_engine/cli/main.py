"""``fi-research`` command line entry point.

Each area contributes a module in ``research_engine.cli`` exposing
``register(subparsers)``; the module registers its subcommands and sets
``func`` on each parser. Missing modules are skipped so partial checkouts work.
"""

from __future__ import annotations

import argparse
import importlib
import sys

AREA_MODULES = (
    "numerical",  # price, curve, risk, scenario, market data/admission
    "simulation",  # replay, resume, report, parity
    "evidence",  # ingest, index, retrieve, benchmark
    "agents",  # decide, research-note
    "experiments",  # experiment register/run/compare/export
    "demo",  # demo build/verify
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fi-research", description="Fixed Income Research Lab command line"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for name in AREA_MODULES:
        try:
            module = importlib.import_module(f"research_engine.cli.{name}")
        except ModuleNotFoundError as exc:
            if exc.name == f"research_engine.cli.{name}":
                continue
            raise
        module.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    result = func(args)
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())
