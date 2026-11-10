"""The committed demo bundle verifies from recorded responses with providers disabled."""

import json

import pytest

from research_engine.cli.main import main
from research_engine.experiments.demo import (
    DEMO_EXPERIMENT_ID,
    DEMO_ROOT,
    ProvidersDisabled,
    providers_disabled,
)

BUNDLE = DEMO_ROOT / DEMO_EXPERIMENT_ID

pytestmark = pytest.mark.skipif(
    not (BUNDLE / "bundle.json").exists(), reason="demo bundle not built"
)


def test_bundle_labels_reference_model_and_recorded_replay():
    bundle = json.loads((BUNDLE / "bundle.json").read_text())
    definition = json.loads((BUNDLE / "definition.json").read_text())
    assert definition["model"]["isHostedLlm"] is False
    assert definition["model"]["modelId"] == "reference-heuristic-v1"
    assert "not a hosted LLM" in bundle["modelDisclosure"]
    canonical = bundle["runs"]["canonical"]
    assert canonical["responseMode"] == "recorded_replay"
    assert canonical["responseSource"] == "recorded_provider_responses"
    capture = json.loads((BUNDLE / "capture" / "manifest.json").read_text())
    assert capture["responseMode"] == "fresh_inference"
    assert capture["responseSource"] == "fresh_provider_calls"
    assert sum(row["bytes"] for row in bundle["files"]) < 15 * 1024 * 1024


def test_providers_disabled_guard_blocks_reference_model():
    from research_engine.agents.providers import ReferenceHeuristicProvider

    with providers_disabled():
        with pytest.raises(ProvidersDisabled):
            ReferenceHeuristicProvider().generate(None)
    assert "generate" in ReferenceHeuristicProvider.__dict__


@pytest.mark.slow
def test_demo_verify_passes_on_committed_bundle(capsys):
    code = main(["demo", "verify", "--verbose"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload["mismatches"]
    assert payload["ok"] and not payload["mismatches"]
    names = {c["check"] for c in payload["checks"]}
    for required in (
        "canonical:strategy_results_identical",
        "canonical:transitions_identical",
        "canonical:final_state_hashes",
        "canonical:report_metrics_identical",
        "stored_results:transitions_identical",
        "failure_injection:strategy_results_identical",
        "failure_injection:report_metrics_identical",
    ):
        assert required in names
