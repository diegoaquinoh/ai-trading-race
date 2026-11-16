"""Evidence CLI: ``ingest fed``, ``index build|validate``, ``retrieve``, ``benchmark build|run``.

All commands use ``--home`` (default ``$FI_RESEARCH_HOME`` or ``~/.cache/fi-research``)
holding ``research.sqlite`` and the content-addressed artifact store;
``$FI_RESEARCH_DB_URL`` switches the research store to SQL Server (schema ``research``).
Network access happens only in ``ingest fed --online`` / ``--refresh-fixtures``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _home(args: argparse.Namespace):  # type: ignore[no-untyped-def]
    from research_engine.evidence.ingest import EvidenceHome

    return EvidenceHome.open(args.home)


def _graph(args: argparse.Namespace):  # type: ignore[no-untyped-def]
    if getattr(args, "graph", "memory") == "neo4j":
        from research_engine.knowledge.neo4j_store import Neo4jGraphStore

        return Neo4jGraphStore(
            os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "local-dev-graph-only"),
        )
    from research_engine.knowledge.graph_store import InMemoryGraphStore

    return InMemoryGraphStore()


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _ingest_fed(args: argparse.Namespace) -> int:
    from research_engine.evidence import fed
    from research_engine.evidence.fetch import AllowlistedFetcher
    from research_engine.evidence.ingest import FedIngestor

    if args.refresh_fixtures:
        entries = fed.fetch_fixtures()
        _print({"fixtures_written": len(entries), "manifest": str(fed.MANIFEST_PATH)})
        return 0
    home = _home(args)
    offline = not args.online
    fetcher = None if offline else AllowlistedFetcher(allowed_hosts=fed.ALLOWED_HOSTS)
    report = FedIngestor(home, offline=offline, fetcher=fetcher).run(
        include_synthetic=args.include_synthetic
    )
    source = home.store.get_source(fed.SOURCE_ID)
    _print(
        {
            "fetch_run": report.fetch_run.to_wire(),
            "new_versions": report.new_version_ids,
            "unchanged": len(report.unchanged_document_ids),
            "failed": report.failed,
            "quarantined": report.quarantined,
            "review_required": report.review_required,
            "calendar_problems": report.calendar_problems,
            "source_health": source.health.to_wire() if source else None,
        }
    )
    return 0 if report.fetch_run.outcome.value != "outage" else 3


def _index_build(args: argparse.Namespace) -> int:
    from research_engine.retrieval.index import activate_index, build_index

    home = _home(args)
    build = build_index(home.store, _graph(args), include_synthetic=args.include_synthetic)
    if build.status.value == "READY" and args.activate:
        if home.store.active_index_id() != build.build_id:
            activate_index(home.store, build.build_id)
    _print(build.to_wire() | {"active": home.store.active_index_id() == build.build_id})
    return 0 if build.status.value == "READY" else 1


def _index_validate(args: argparse.Namespace) -> int:
    from research_engine.knowledge.graph_store import InMemoryGraphStore
    from research_engine.retrieval.index import IndexNotReady, load_index, rebuild_graph

    home = _home(args)
    build_id = args.build_id or home.store.active_index_id()
    if not build_id:
        print("no build id given and no active index", file=sys.stderr)
        return 1
    try:
        index = load_index(home.store, build_id, graph=_graph(args))
    except IndexNotReady as exc:
        _print({"build_id": build_id, "valid": False, "error": str(exc)})
        return 1
    # Independent rebuild into a fresh in-memory backend: membership must match.
    fresh = InMemoryGraphStore()
    rebuilt = rebuild_graph(home.store, index.build, fresh)
    loaded_nodes, loaded_assertions = (
        index.graph.membership(build_id) if index.graph else (set(), set())
    )
    same = (frozenset(loaded_nodes), frozenset(loaded_assertions)) == rebuilt.membership()
    _print(
        {
            "build_id": build_id,
            "status": index.build.status.value,
            "embedding_matrix_reproduced": True,
            "graph_error": index.graph_error,
            "graph_rebuild_membership_equal": same,
            "nodes": len(rebuilt.nodes),
            "assertions": len(rebuilt.assertions),
            "validation_checks": index.build.validation_checks,
        }
    )
    return 0 if same and not index.graph_error else 1


def _retrieve(args: argparse.Namespace) -> int:
    from research_engine.contracts.evidence import RetrievalRequest
    from research_engine.retrieval.index import load_index
    from research_engine.retrieval.service import retrieve

    home = _home(args)
    build_id = args.build_id or home.store.active_index_id()
    if not build_id:
        print("no active index: run `fi-research index build --activate` first", file=sys.stderr)
        return 1
    index = load_index(home.store, build_id, graph=_graph(args))
    request = RetrievalRequest(
        question=args.question,
        decision_as_of=args.as_of,
        mode=args.mode,
        index_build_id=build_id,
        explicit_identifiers=args.identifier or [],
    )
    run, bundle = retrieve(request, home.store, index)
    if args.json:
        _print({"run": run.to_wire(), "bundle": bundle.to_wire()})
        return 0
    print(f"run {run.retrieval_run_id}  bundle {bundle.bundle_id}  snapshot {run.snapshot_id}")
    print(
        f"cutoff {args.as_of}  mode {request.mode.value}  "
        f"chunks {bundle.chunk_count}  tokens {bundle.total_tokens}"
    )
    for chunk in bundle.chunks:
        prov = chunk.provenance
        graph = ""
        if prov.graph:
            graph = f" graph(seed={prov.graph.seed_id}, added={prov.graph.added_by_graph})"
        print(
            f"#{prov.final_rank:>3} {chunk.chunk_id} {chunk.document_id} "
            f"[{' > '.join(chunk.heading_path)[-60:]}] "
            f"{','.join(c.value for c in prov.channels)}{graph}"
        )
        print(
            "      "
            + chunk.text[:160].replace("\n", " ")
            + ("..." if len(chunk.text) > 160 else "")
        )
    for fact in bundle.structured_facts[:8]:
        print(f"fact {fact.relation.value}: {fact.subject_label} -> {fact.object_label}")
    return 0


def _benchmark_index(args: argparse.Namespace):  # type: ignore[no-untyped-def]
    from research_engine.retrieval import open_default_evidence

    return open_default_evidence(args.home, include_synthetic=True)


def _benchmark_build(args: argparse.Namespace) -> int:
    from research_engine.retrieval import benchmark

    _, index = _benchmark_index(args)
    data = benchmark.generate(index)
    target = Path(args.output) if args.output else benchmark.QUESTIONS_PATH
    target.write_text(json.dumps(data, indent=2) + "\n")
    print(f"wrote {len(data['questions'])} questions to {target}")
    return 0


def _benchmark_run(args: argparse.Namespace) -> int:
    from research_engine.retrieval import benchmark

    home, index = _benchmark_index(args)
    report = benchmark.evaluate(home.store, index, split=args.split)
    report["generated_at"] = datetime.now().astimezone().isoformat()
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.output}")
    _print(report["summary"])
    violations = report["summary"]["all"]
    bad = any(violations[m]["temporal_violations"] for m in ("hybrid_rag_v1", "graph_rag_v1"))
    return 1 if bad else 0


def register(subparsers: argparse._SubParsersAction) -> None:
    def home_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--home", default=None, help="evidence home (default $FI_RESEARCH_HOME)")

    ingest = subparsers.add_parser("ingest", help="source ingestion")
    ingest_sub = ingest.add_subparsers(dest="ingest_command", metavar="<source>")
    fed_p = ingest_sub.add_parser("fed", help="Federal Reserve FOMC statements and minutes")
    home_arg(fed_p)
    mode = fed_p.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", default=True, help="use fixtures (default)")
    mode.add_argument("--online", action="store_true", help="NETWORK: fetch www.federalreserve.gov")
    fed_p.add_argument(
        "--include-synthetic", action="store_true", help="add the labelled synthetic correction"
    )
    fed_p.add_argument(
        "--refresh-fixtures", action="store_true", help="NETWORK: write raw fixtures + manifest"
    )
    fed_p.set_defaults(func=_ingest_fed)

    index = subparsers.add_parser("index", help="evidence index builds")
    index_sub = index.add_subparsers(dest="index_command", metavar="<action>")
    build = index_sub.add_parser("build", help="build + validate an index (READY only if valid)")
    home_arg(build)
    build.add_argument("--include-synthetic", action="store_true")
    build.add_argument("--activate", action="store_true", help="publish as the active manifest")
    build.add_argument("--graph", choices=["memory", "neo4j"], default="memory")
    build.set_defaults(func=_index_build)
    validate = index_sub.add_parser(
        "validate", help="reload, recompute and rebuild-compare a build"
    )
    home_arg(validate)
    validate.add_argument("--build-id", default=None)
    validate.add_argument("--graph", choices=["memory", "neo4j"], default="memory")
    validate.set_defaults(func=_index_validate)

    ret = subparsers.add_parser("retrieve", help="retrieve an eligible evidence bundle")
    home_arg(ret)
    ret.add_argument("--question", required=True)
    ret.add_argument(
        "--as-of", required=True, help="decision_as_of instant, e.g. 2024-02-01T00:00:00Z"
    )
    ret.add_argument(
        "--mode", default="hybrid_rag_v1", choices=["none", "hybrid_rag_v1", "graph_rag_v1"]
    )
    ret.add_argument("--build-id", default=None)
    ret.add_argument(
        "--identifier", action="append", help="explicit identifier (event/document id)"
    )
    ret.add_argument("--graph", choices=["memory", "neo4j"], default="memory")
    ret.add_argument("--json", action="store_true")
    ret.set_defaults(func=_retrieve)

    bench = subparsers.add_parser("benchmark", help="evidence benchmark")
    bench_sub = bench.add_subparsers(dest="benchmark_command", metavar="<action>")
    run = bench_sub.add_parser("run", help="evaluate hybrid and graph retrieval")
    home_arg(run)
    run.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    run.add_argument("--output", default=None)
    run.set_defaults(func=_benchmark_run)
    gen = bench_sub.add_parser("build", help="regenerate questions_v1.json from the corpus")
    home_arg(gen)
    gen.add_argument("--output", default=None)
    gen.set_defaults(func=_benchmark_build)
