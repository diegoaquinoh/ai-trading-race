# Provenance and time policy (evidence)

Applies spec section 6 to documents, chunks, graph assertions, aliases and
retrieval. Implementation: `research_engine/evidence/fed.py`,
`evidence/ingest.py`, `knowledge/extraction.py`, `retrieval/snapshot.py`.

## Time fields

| Field | Evidence meaning | Stored on |
|---|---|---|
| `published_at` | When the source made the document public (reconstructed for history) | DocumentVersion |
| `published_at_precision` | `minute` or `date` | DocumentVersion |
| `publication_timezone` | IANA zone of the source schedule (`America/New_York`) | DocumentVersion |
| `publication_time_basis` | Rule and evidence that established `published_at` | DocumentVersion |
| `available_at` | Earliest permitted use under the declared policy | DocumentVersion, Chunk, Entity, EntityAlias, RelationshipAssertion, GraphNode |
| `availability_policy` | Policy id that produced `available_at` | DocumentVersion |
| `ingested_at` | When the platform obtained the bytes | DocumentVersion |
| `decision_as_of` | Strict information cutoff for a retrieval | RetrievalRequest, EvidenceBundle |
| `generated_at` | Operational time a derived record was produced (never used for eligibility) | ExtractionRun, retrieval row |

All instants are UTC (`...Z`). Meeting dates and CPI reference periods are not
publication times.

## Policies

### `reconstructed_publication_plus_lag_v1` (historical replay)

`available_at = published_at + 120 minutes` — a declared conservative
acquisition/processing lag. Runs using it are reconstructed-availability runs
(spec 6.2) and must be labelled so.

| Source | `published_at` rule (`fomc_release_1400_et_v1`) | Evidence |
|---|---|---|
| FOMC statement | 14:00 America/New_York on the final meeting day | The page's own "For release at 2:00 p.m. EST/EDT" line; a page that does not confirm it is `review_required` |
| FOMC minutes | 14:00 America/New_York on the release date from the FOMC calendar ("Released …") | Calendar fixture; the pinned table is validated against it in tests |
| CPI release (graph node) | 08:30 America/New_York on the BLS release date | BLS archive URLs (dates only stored) |

Daylight saving time is applied through `zoneinfo` (e.g. 2023-02-01 statement
→ 19:00Z, available 21:00Z; 2023-06-14 → 18:00Z, available 20:00Z).

Consequences tested in `tests/evidence/test_temporal.py`:

- Minutes are never eligible on their meeting's statement date (about three
  weeks earlier); they become eligible exactly at release + 120 minutes.
- PolicyEvent nodes and their aliases become available with the statement, so
  "the March 2023 meeting" does not resolve before 2023-03-22 20:00Z.

### `forward_receipt_v1` (forward runs and detected revisions)

`available_at = max(published_at, platform receipt)`. Used for online refreshes
and for any page whose normalized text changed after first ingestion: the new
version's original publication time is unknown, so it is available only from
receipt, and it `SUPERSEDES` the earlier version without overwriting it.

## Fidelity flags

- `current_web_version_not_archived_original`: every fixture page was fetched in
  November 2026 (`Last-Modified` headers are 2026 dates). They are not archived
  copies of the original releases and are not presented as the original
  historical text (spec 6.2). Bundles carry the flag to agents and reviewers.
- `synthetic_test_fixture_not_a_federal_reserve_publication`: the single
  synthetic correction (2023-03-22 statement, available 2023-03-29 20:00Z,
  `synthetic = true`, title suffix `[SYNTHETIC CORRECTION]`). It is included only
  when explicitly requested (tests, benchmark) and excluded from default indexes.

## Corrections and immutability

- Canonical records (versions, chunks, assertions, runs, bundles) are
  content-addressed and immutable; re-inserting different content under an
  existing id raises `ImmutableRecordConflict`.
- A correction is a new `DocumentVersion` with `supersedes = <old version>`.
  The eligible snapshot at cutoff `t` uses the latest version that is itself
  eligible at `t`; a correction available after `t` never changes the text used
  at `t`, and saved retrieval runs/bundles are never rewritten.
- Index builds are immutable manifests of exact member version ids. Rolling back
  is activating an earlier READY build.

## Derived-data leakage controls (spec 6.3)

| Risk | Control |
|---|---|
| Graph edges built from future documents | Assertion `available_at` = latest `available_at` of all inputs; traversal filters assertions *and* neighbour nodes by the cutoff and by snapshot membership |
| Graph degree / neighbour order changing with future additions | Fanout ordering uses relation round-robin, snapshot passage relevance, recency and id — never degree; tests compare a small (past-only) index with the full index at the same cutoff and require identical seeds, visited assertions, limits, candidates and bundles |
| Lexical statistics from the future | BM25 N, df and average length come from the eligible snapshot only |
| ANN index containing future chunks | Exact cosine over snapshot chunks; hash embeddings use no corpus statistics |
| Aliases/entity resolution learned later | Aliases are versioned with `available_at`; the latest version visible at the cutoff wins; later aliases (`recalibration`, `SVB`) and remaps cannot affect earlier cutoffs |
| Query templates/vocabulary fitted on data | Topic vocabulary and lexicon are hand-curated and frozen (`topic-vocab-v1`, `rule_lexicon_v1`); no LLM expansion |
| Caches crossing cutoffs or scopes | Cache key = cutoff, snapshot id, build id, embedding model, algorithm versions, full request, permission scope |
| Pretrained-model hindsight | Not solvable by retrieval; downstream LLM runs must be labelled retrospective (spec 6.3) |

## Source freshness

A `SourceFetchRun` is recorded for every refresh. Only `success` advances
`last_success_at`, and only to the time the content was actually observed
(fetch time online, fixture capture time offline). `outage` and `partial` runs
update `last_attempt_at`, the failure counter and the error, leave the corpus
untouched, and set health to `outage` or `degraded`. `state.freshness(source,
now)` reports `stale` when the last success is older than the registry's
freshness expectation, regardless of later failed attempts.

## Provenance chain for a delivered passage

`DeliveredChunk` → `chunk_id` (text hash, offsets into the stored normalized
text) → `version_id` (raw artifact `artifact://sha256/…`, normalized artifact,
parser version, `published_at`/`available_at`/policy, fidelity flags, source URL)
→ `document_id` → `source_id` (registry entry) → raw fixture manifest checksum.
Graph passages add the seed, the traversed assertion ids with their support
spans or source rows, and an availability check per record.
