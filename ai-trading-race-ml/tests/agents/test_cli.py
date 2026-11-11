"""``fi-research decide | research-note | record`` registration and an offline decide run."""

from __future__ import annotations

import json

from research_engine.cli.main import build_parser, main


def test_agent_commands_are_registered():
    parser = build_parser()
    args = parser.parse_args(
        [
            "decide",
            "--strategy",
            "llm_team",
            "--date",
            "2023-06-14",
            "--provider",
            "recorded",
            "--recordings",
            "x",
        ]
    )
    assert args.strategy == "llm_team" and args.provider == "recorded"
    args = parser.parse_args(["research-note", "--question", "q", "--as-of", "2023-06-14"])
    assert args.mode == "graph" and args.provider == "reference"
    args = parser.parse_args(
        ["record", "--experiment", "e", "--from", "2023-06-12", "--to", "2023-06-14"]
    )
    assert str(args.from_date) == "2023-06-12"


def test_decide_market_strategy_offline(tmp_path, capsys):
    out = tmp_path / "result.json"
    code = main(["decide", "--strategy", "llm_market", "--date", "2023-06-14", "--out", str(out)])
    assert code == 0
    result = json.loads(out.read_text())
    assert result["strategyId"] == "llm_market"
    assert result["versions"]["provider"] == "reference"
    assert result["outcome"] in ("completed_proposal", "completed_hold")
    assert result["resultHash"] and result["signature"]
