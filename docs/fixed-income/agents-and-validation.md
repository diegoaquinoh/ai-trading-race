# AI strategies, specialist team, tools, budgets and validation

Implements spec §10, §13, §14.4–14.6, §15.2–15.3, §16.2, §16.6 and §18.4 (milestones M3 and M6).
Code: `ai-trading-race-ml/research_engine/agents/`, CLI `research_engine/cli/agents.py`, tests
`tests/agents/`, recorded responses `fixtures/recorded/`.

> **No hosted model was used to build or test this.** Demos and tests run on
> `reference-heuristic-v1`, a deterministic, offline, rule-based policy model. It is reported as provider
> `reference` everywhere and is **not** an LLM. The Anthropic and OpenAI-compatible clients are tested
> only against mocked HTTP transports.

## Strategies

| Strategy | Kind | Retrieval | Tools |
|---|---|---|---|
| `llm_market` | single agent | none | numerical tools only; never receives document text |
| `llm_rag` | single agent | `hybrid_rag_v1` | + `retrieve_evidence` (mandatory first call) |
| `llm_graph` | single agent | `graph_rag_v1` | + `expand_evidence_graph` |
| `llm_team` | lead + `macro_researcher` + `critical_reviewer` | `graph_rag_v1` | same evidence access as `llm_graph` |

All four share the prompt set (`fi-agent-prompts-v1@<hash>`), output contract (`agent-output-v1`), tool
schemas (`fi-agent-tools-v1`), validation pipeline (`proposal-validation-v1`), risk policy and
provider/model, so the retrieval and delegation comparisons are controlled (§10.2). Only the allowed
tools and the evidence delivered differ. Invested strategies receive the common bootstrap allocation with
no model call.

Construction:

```python
import research_engine.agents as agents          # registers llm_* with the strategy registry
provider = agents.build_provider("reference")      # | "recorded" (recordings=dir) | "anthropic" | "openai"
evidence = agents.open_default_evidence_port(home)  # offline Fed corpus + READY index
strategies = agents.build_llm_strategies(provider=provider, evidence=evidence)
ReplayRunner(config, pricing, market, run_dir, key, strategies=strategies)
```

`create_strategy("llm_rag", config)` also works after the import; it resolves the provider from
`config["provider"]` (default `reference`) and opens the default evidence index. The strategy config
records provider label, pinned model id, prompt/tool versions, retrieval mode, index build and workflow
limits; its hash is `versions.strategyConfigHash`. The response *source* (live, recording capture or
recorded replay) is injected at runtime and is not part of the config, so a recorded replay reproduces
the captured StrategyResults byte for byte.

Hosted providers: `AnthropicProvider` (Messages API over httpx, `anthropic-version: 2026-10-21`, pinned
model default `claude-sonnet-5-5`, key from `ANTHROPIC_API_KEY`, structured output through
`output_config.format`, no sampling parameters) and `OpenAICompatibleProvider` (OpenAI, Azure OpenAI
deployments, Groq-hosted Llama, local servers; strict `json_schema` response format). A fresh priced run
is refused (`failed_dependency`) unless a versioned `PriceSchedule` containing the model and a monetary
ceiling (`maxCostUsd` or `budget.maxCostUsd`) are configured (§10.4). Prices are never shipped as
defaults; the operator supplies them.

## Single-agent workflow (§10.3)

1. Required tools on the frozen snapshot: `get_portfolio_risk`, `get_market_features`.
2. Evidence strategies: mandatory `retrieve_evidence` with the fixed template `policy-outlook-v1`
   (initial budget 6 chunks / 4,000 evidence tokens, identical for rag/graph/team).
3. Up to two tool-selection turns, then a forced synthesis turn.
4. Validation; blocking failures and malformed replies may be repaired (two repairs by default) while
   the decision budget lasts. The first fully valid response is selected; every attempt is kept.

## Team workflow (§10.4)

* The lead runs steps 1–2, then a `task_assignment` turn from the evidence index (passage text reaches the
  lead once, at synthesis). It may decline delegation.
* At most `maxSpecialistInvocations` (2) tasks to registered roles; depth one (specialists cannot
  delegate; a `delegate` reply from a specialist is malformed). Unregistered, duplicate and over-limit
  tasks are recorded as `skipped` with the reason.
* Before specialist work the lead reserves its synthesis capacity on the ledger; the rest is split into
  deterministic per-task allowances (call counts evenly; tokens and evidence 0.6/0.4 macro/reviewer,
  remainder to the larger share). The sum of allowances never exceeds what is left, so concurrent
  specialists cannot overspend and denials do not depend on thread scheduling.
* The reviewer workflow is a versioned config value, one per run: `parallel_v1` (default; specialists run
  concurrently on the research question and current exposures) or `sequential_on_draft_v1` (macro
  researcher, lead draft, reviewer challenges the draft). The macro researcher receives the delivered
  passages; the reviewer works from exposures, scenarios and the evidence index.
* The task tree (`specialistTasks`) records task ids, instruction, input snapshot ids, expected output
  schema, reserved block, status, concise findings, claim ids and usage. No chain-of-thought is
  requested or stored.

Under the budget-matched ceiling (32,000 input tokens) `parallel_v1` completes with the reference model
(~25k input tokens per decision). `sequential_on_draft_v1` resends the lead conversation twice and
exceeds 32k: the reviewer task is denied (`denied_budget`) and the lead still synthesizes. Use a declared
capability-track budget for that variant.

## Budget ledger (§10.4)

One thread-safe `BudgetLedger` per decision covers generation calls (task assignment, tool selection,
specialist turns, synthesis, malformed replies and repairs), tool calls, evidence calls (shared by
`retrieve_evidence` and `expand_evidence_graph`), unique evidence chunks (a repeated chunk counts once),
evidence tokens, input/output tokens (every resend counts), monetary cost via a versioned price schedule
and the deadline. `reserve` atomically checks committed + outstanding + requested ≤ limit; `commit`
records actual usage (even above the reservation, which marks the ledger exhausted); `release` drops an
unused reservation. Provider reservations use the `char3.5-upper-v1` estimate. Every provider reservation
is settled exactly once: a failed call (refusal, HTTP or transport error) commits one generation call plus
the usage the provider reported for it (a refusal still bills its tokens), and any unexpected exception
commits the attempted call in a `finally` so no reservation keeps holding budget. A denial for the lead or
single agent ends the decision `failed_budget` with consumed resources in `usage`; a specialist denial
ends that task `denied_budget`.

## Tools (§10.5, §18.4)

`get_instrument_terms`, `get_market_features`, `get_valuation`, `get_portfolio_risk`, `run_scenario`,
`retrieve_evidence`, `expand_evidence_graph`, `propose_targets`. Typed Pydantic arguments with extra fields
forbidden; snapshot, curve, cutoff, index and portfolio are bound by the toolbox, never arguments.
Scenarios are limited to `scenario_library_v1`; graph seeds to ids already delivered to the decision.
Numerical outputs are registered as signed calculations and returned by id (`market-features-v1` and
`agent-portfolio-risk-v1` are registered by the toolbox; prices, risk and scenarios by the pricing port).
`get_market_features` returns curve levels, 1/5/21-session changes and optional vintage-aware macro values
only, registered as calculation type `market_features`. `propose_targets` is a policy dry run that keeps no order intents. Unknown or disallowed tools are
recorded as `denied_policy`.

Retrieved passages are rendered as `<untrusted_document chunk_id="…">` blocks next to trusted
`<platform_json>` blocks; tag-like text inside documents is neutralized. Instructions in documents cannot
change permissions (enforced by the toolbox) or targets (enforced by validation and the policy dry run).

## Validation pipeline (§13.2) and outcomes (§15.2)

Recorded per attempt as `ValidationResult`s (first detail `attempt:<id>`), plus an `original_proposal`
record holding each attempt's proposal JSON:

1. `schema` – ids, cross-references, decision/proposal consistency, finite weights in [0,1] over the frozen
   universe plus cash, `Proposal` contract (sum to 1).
2. `citation_membership` – chunk delivered in that exact bundle, same document version.
3. `temporal` – `availableAt ≤ decisionAsOf`, bundle cutoff, permitted index build and retrieval mode.
4. `quote_offsets` – exact quote/offsets against delivered normalized text, which must equal the stored
   chunk text.
5. `calc_refs` – exists in the signed CalculationStore, signature verifies, issued to this decision, not
   after the cutoff. A model cannot mint a trusted id.
6. `support` – `support-lexical-v1` review aid (claim-token overlap with cited quotes/titles, threshold
   0.5). It is a flag, not proof.
7. `policy` – sizing, funding and risk via the simulation policy dry run.

| Condition | Outcome |
|---|---|
| invalid dependent claim/calculation, policy rejection, malformed after repairs | `failed_invalid_output` (no proposal) |
| flagged material dependency | `review_required` |
| empty mandatory retrieval | `abstained_insufficient_evidence` (default) or `review_required` (`onInsufficientEvidence`) |
| contradictory evidence | `review_required` (default) or `abstained_insufficient_evidence` (`onContradictoryEvidence`) |
| graph index failure in `llm_graph`/`llm_team` | `failed_dependency` (`graph_retrieval_unavailable`, `no_fallback_to_hybrid_rag_v1`) |
| provider error after bounded retries, missing recording | `failed_dependency` |
| budget exhaustion | `failed_budget` |
| explicit model HOLD with supported status | `completed_hold` |
| valid REBALANCE | `completed_proposal` with `policyEvaluation` |

Only `completed_proposal` is submitted by the runner, so a malformed or invalid proposal never produces a
financial transition.

## Result envelope (§14.5)

Attempts (numbered in deterministic order), tool traces, specialist task tree, usage, versions
(provider, model, prompt version, tool schema, index build, retrieval mode, config hash), evidence bundle
ids, request and input hashes (decision request, portfolio, market, risk policy, strategy config, prompt
set, tool schema, evidence bundles), `resultHash = content_hash(hash_payload())` and
`signature = HMAC(resultHash)` with `FI_RESULT_SIGNING_KEY` (development key with a warning when unset).
Timing defaults to `logical` (timestamps at the decision cutoff, model latency from the provider or
recording, tool durations 0) so replays are reproducible; `timing: wall` measures wall time.

## Research notes

`research_note(question, as_of, evidence=…, provider=…, pricing=…, market=…, portfolio_state=None)`
retrieves with the question as the query (`graph_rag_v1` by default), allows one tool turn and returns a
signed `ResearchNoteResult` with `orderAuthority: false`. The note contract has no proposal field and
`propose_targets` is unavailable.

## Recorded responses

`RecordingProvider` stores each response under `<fingerprint>#<occurrence>`. The fingerprint hashes the
decision id, role, attempt purpose, prompt version and the exact messages (system, messages, output
schema). `RecordedResponseProvider` replays them without provider access and raises `RecordingMissing`
when a request changes. Request texts are not stored, only their hashes.

```bash
fi-research record --experiment demo-sample-2023-06 --from 2023-06-13 --to 2023-06-16   # capture + verify
fi-research decide --strategy llm_team --date 2023-06-14 [--provider reference|recorded|anthropic|openai]
fi-research research-note --question "What did the FOMC say about inflation?" --as-of 2023-06-20
```

`fixtures/recorded/demo-sample-2023-06/` is the committed sample: 4 strategies × 4 sessions and 33
recorded reference responses. `record_experiment` runs two separate modes (spec §6.5): a **capture**
(`fresh_inference` of the reference model through `RecordingProvider`; `capture/config.json` and
`capture/manifest.json`) and a **recorded-response replay** (`recorded_replay` with
`replay_source=recorded_responses` on `RecordedResponseProvider`; `run/config.json`, `outcomes.jsonl`,
`manifest.json`). The two must agree on every decision; only the request binding (`requestHash`,
`inputHashes.decisionRequest`, `resultHash`, `signature`) differs, because the DecisionRequest carries
the response mode. `experiment.json` records the disclosure, versions, `decisionId → resultHash` and
`captureReplayEquivalent`. `replay_experiment` re-runs the replay from the recordings and checks every
StrategyResult for equality (`tests/agents/test_recorded_replay.py`). Fixture signatures use published,
non-secret keys. The sample was re-recorded on 2026-11-09 after market features became
`CalculationType.MARKET_FEATURES` (calculation ids are content-addressed, so recordings changed).

Runner response modes (`ReplayConfig.response_mode` + `replay_source`):

| Mode | Strategies called? | Provider | Manifest `responseSource` |
|---|---|---|---|
| `fresh_inference` | yes | live or reference (a replay-only provider is refused) | `fresh_provider_calls` |
| `recorded_replay` + `recorded_responses` | yes | replay-only (`provider.replay`; a live provider is refused) | `recorded_provider_responses` |
| `recorded_replay` + `stored_results` (default) | no; persisted StrategyResults are re-validated | none | `stored_strategy_results` |

Each strategy entry in the manifest also carries `responseSource` (`deterministic_code`,
`provider_call:<provider>/<model>[:captured]`, `recorded_responses:<provider>/<model>`,
`stored_strategy_result`). The demo bundle (`fixtures/demo/fi-demo-2024q1/`, see
[reports/demo-experiment.md](reports/demo-experiment.md)) uses the same protocol for all seven competitors.

## Limitations

* The reference model is a lexicon rule, not an LLM. Comparisons between strategies under it measure
  plumbing and evidence access, not model reasoning.
* Hosted clients are verified only against mocked transports. Live behaviour, token counts and refusals
  need a credentialed run with an operator-supplied price schedule.
* Market features carry no macro series by default. A vintage-aware `MacroFeatureSource` can be injected,
  but none is configured because the bundled ALFRED fixture is illustrative.
* The support classifier is lexical. It flags low overlap and cannot detect entailment.
* Pretrained models may know later outcomes (§6.3). Retrospective LLM runs must be labelled as such.
