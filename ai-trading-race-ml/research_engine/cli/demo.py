"""``fi-research demo build | verify`` - the recorded demo bundle (spec 17.6, milestone M7).

* ``demo build`` registers the demo experiment (``fi-demo-2024q1``), captures
  reference-model responses (``fresh_inference`` through a recording provider),
  re-runs the experiment as a recorded-response replay (the canonical run),
  runs the separately labelled failure-injection run and the half-spread
  sensitivity reruns, and writes the bundle under
  ``ai-trading-race-ml/fixtures/demo/fi-demo-2024q1/``.
* ``demo verify`` replays the bundle from its recorded responses with every
  provider disabled and checks identical StrategyResults, transitions, state
  hashes, report metrics and evidence comparisons. Exit code 1 on any mismatch.

AI strategies run on provider ``reference`` (``reference-heuristic-v1``), a
deterministic rule-based policy model - not a hosted LLM. No credentials or
network access are needed; evidence comes from the offline Fed fixtures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _log(message: str) -> None:
    print(f"[demo] {message}", file=sys.stderr)


def _cmd_build(args) -> int:
    from research_engine.experiments.demo import DEMO_ROOT, build_demo

    bundle = build_demo(
        Path(args.out_root) if args.out_root else DEMO_ROOT,
        home=Path(args.home) if args.home else None,
        overwrite=args.overwrite,
        sensitivity=not args.skip_sensitivity,
        log=_log,
    )
    size = sum(row["bytes"] for row in bundle["files"])
    print(
        json.dumps(
            {
                "experimentId": bundle["experimentId"],
                "files": len(bundle["files"]),
                "bytes": size,
                "canonical": bundle["runs"]["canonical"]["expected"]["status"],
                "failureInjection": bundle["runs"]["failureInjection"]["expected"]["status"],
                "sensitivity": bundle["sensitivity"],
            },
            indent=2,
        )
    )
    return 0


def _cmd_verify(args) -> int:
    from research_engine.experiments.demo import DEMO_EXPERIMENT_ID, DEMO_ROOT, verify_demo

    bundle_dir = Path(args.bundle) if args.bundle else DEMO_ROOT / DEMO_EXPERIMENT_ID
    if not (bundle_dir / "bundle.json").exists():
        print(
            f"error: no demo bundle at {bundle_dir}; run `fi-research demo build`", file=sys.stderr
        )
        return 2
    result = verify_demo(bundle_dir, home=Path(args.home) if args.home else None, log=_log)
    payload = result.to_dict()
    if not args.verbose:
        payload["checks"] = f"{sum(c['passed'] for c in result.checks)}/{len(result.checks)} passed"
    print(json.dumps(payload, indent=2))
    return 0 if result.ok else 1


def register(subparsers) -> None:
    demo = subparsers.add_parser("demo", help="recorded demo bundle (build / verify)")
    demo_sub = demo.add_subparsers(dest="demo_command", metavar="<action>")

    build = demo_sub.add_parser("build", help="register, run, record and package the demo")
    build.add_argument("--out-root", help="default ai-trading-race-ml/fixtures/demo")
    build.add_argument("--home", help="evidence home (default: a temporary directory)")
    build.add_argument("--overwrite", action="store_true", help="replace an existing bundle")
    build.add_argument(
        "--skip-sensitivity", action="store_true", help="skip the half-spread reruns"
    )
    build.set_defaults(func=_cmd_build)

    verify = demo_sub.add_parser(
        "verify", help="replay the bundle from recorded responses with providers disabled"
    )
    verify.add_argument("--bundle", help="bundle directory (default: the committed demo bundle)")
    verify.add_argument("--home", help="evidence home (default: a temporary directory)")
    verify.add_argument("--verbose", action="store_true", help="print every check")
    verify.set_defaults(func=_cmd_verify)
