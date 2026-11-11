# Evidence, knowledge graph and retrieval (workstream B: M4, M5)

Implements spec sections 5.4, 11, 12, 13.2–13.3, 15.4 (graph rebuild), 16.4,
16.6 and 18.4–18.5 for the Python research engine
(`ai-trading-race-ml/research_engine/{evidence,knowledge,retrieval}`).
Time and availability rules are in
[provenance-and-time-policy.md](provenance-and-time-policy.md).

No component in this workstream calls an LLM. Extraction is metadata and a
versioned rule lexicon; query construction is deterministic; reranking is off.

## Quick start (offline, no network, no Neo4j)

```bash
cd ai-trading-race-ml
.venv/bin/python -m research_engine ingest fed --offline          # 32 Fed documents from fixtures
.venv/bin/python -m research_engine index build --activate        # validate, then READY
.venv/bin/python -m research_engine index validate                # reload + rebuild-and-compare
.venv/bin/python -m research_engine retrieve \
    --question "What did the minutes of the meeting before the May 2023 meeting say about the labor market?" \
    --as-of 2023-05-03T23:30:00Z --mode graph_rag_v1
.venv/bin/python -m research_engine benchmark run --split dev
.venv/bin/python -m pytest tests/evidence -q
```

`--home` (or `FI_RESEARCH_HOME`, default `~/.cache/fi-research`) holds
`research.sqlite` and the artifact store. `FI_RESEARCH_DB_URL` points the
research store at SQL Server instead (schema `research`).

From Python (other workstreams):

```python
from research_engine.retrieval import open_default_evidence, retrieve, resolve_chunk, validate_quote, validate_citation
from research_engine.contracts.evidence import RetrievalRequest

home, index = open_default_evidence()            # idempotent offline ingest + READY index
run, bundle = retrieve(
    RetrievalRequest(question="...", decision_as_of="2024-02-01T00:00:00Z",
                     mode="graph_rag_v1", index_build_id=index.build_id),
    home.store, index)
chunk = resolve_chunk(home.store, bundle.chunks[0].chunk_id)
check = validate_quote(chunk.text, quote="...", start_offset=None, end_offset=None)
results = validate_citation(citation, bundle, home.store)   # list[ValidationResult]
```

`retrieve` raises `IndexNotReady` for a missing/non-READY/mismatched build and
`GraphRetrievalUnavailable` when graph mode cannot use its graph. It never
falls back from `graph_rag_v1` to plain RAG (spec 13.3).

## Components

| Module | Responsibility |
|---|---|
| `contracts/evidence.py` | Source, Document, DocumentVersion, Chunk, Entity, EntityAlias, RelationshipAssertion, ExtractionRun, IndexBuild, RetrievalRequest/Run, EvidenceBundle (camelCase, float-free; scores are 10-decimal strings) |
| `evidence/artifacts.py` | Content-addressed immutable store, `artifact://sha256/<hex>`, atomic writes, verify on read |
| `evidence/store.py` | SQLAlchemy Core research store (SQLite default, SQL Server schema `research`), immutable records, `schema_version`, numbered migrations |
| `evidence/fetch.py` | https-only exact-host allowlist, manual redirect re-validation, bounded retries, politeness delay |
| `evidence/parsing.py` | bs4 HTML → offset-mapped normalized text; text-layer PDF adapter that quarantines (no OCR) |
| `evidence/chunking.py` | `ws-regex-v1` tokenizer, `section-v1` chunker |
| `evidence/fed.py` | FOMC adapter: pinned meetings validated against the calendar, timestamp rule, fixture capture |
| `evidence/state.py`, `evidence/ingest.py` | Ingestion state machine, attempts, fetch runs, source health, pipeline |
| `knowledge/ontology.py` | `fi-graph-v1` node/relationship types, signatures, approved traversal steps |
| `knowledge/vocabulary.py`, `resolver.py` | Frozen topic/series vocabulary, versioned alias table, time-filtered resolution |
| `knowledge/extraction.py` | `metadata_v1`, `event_series_v1`, `rule_lexicon_v1`, `release_fixture_v1` |
| `knowledge/graph_store.py`, `neo4j_store.py` | Projection, in-memory backend (default), Neo4j backend |
| `retrieval/index.py` | IndexBuild create → validate → READY/FAILED, load, graph rebuild |
| `retrieval/snapshot.py` | Eligible snapshot, snapshot-local BM25, exact cosine |
| `retrieval/query.py`, `graph.py`, `service.py`, `citations.py` | Query construction, graph expansion, `retrieve`, citation checks |
| `retrieval/benchmark.py` | Benchmark generation and evaluation |
| `cli/evidence.py` | `ingest fed`, `index build|validate`, `retrieve`, `benchmark build|run` |

## Source registry and ingestion

The registry entry for `fed-fomc` (`fed.fed_source()`, stored in `sources`)
declares owner, allowed hosts (`www.federalreserve.gov`), discovery method
(`pinned_list_validated_by_calendar`), document types, cadence, parser and
adapter versions, timestamp rule (`fomc_release_1400_et_v1`), availability
policy and lag, retry limits and a freshness expectation (60 days).

State machine (every attempt is an `IngestionAttempt` row, including unchanged
re-fetches):

```text
discovered -> downloaded -> parsed -> chunked -> extracted -> indexed -> active
                  \-> failed_retryable / quarantined / review_required
```

- Raw bytes are stored before normalization. Identical bytes with the same
  parser version are reused without reparsing; different bytes with identical
  normalized text reuse the existing version (attempt notes the raw change).
- A changed page creates a new version that `SUPERSEDES` the old one and is
  available only from receipt time (`forward_receipt_v1`): the original
  publication time of a silent revision is unknown.
- 404 → `quarantined` (visible coverage gap); transport/5xx after retries →
  `failed_retryable`; a statement whose page does not confirm the 2:00 p.m.
  release → `review_required`, excluded from indexes.
- Each refresh is a `SourceFetchRun` (`success`, `partial`, `outage`). Only a
  successful run advances `last_success_at`, and it advances it to the time the
  source content was actually observed (fixture capture time offline), never to
  wall time. An outage leaves the corpus and freshness untouched and is visible
  in source health (`outage`, consecutive failures, last error).

## Normalized text, chunks and citations

- `normalized-text-v1`: blocks separated by a blank line, `<br>` → newline,
  whitespace collapsed, zero-width format characters removed, NFC. Each block
  records its span and an HTML `line/col/tag` (or PDF stream) locator.
- `ws-regex-v1` token = word run with internal `' ’ . / -` (`5-1/4`,
  `Committee's`) or one punctuation character. It is a counting tokenizer for
  budgets, not a model tokenizer.
- `section-v1`: chunks never cross a heading or a version; target 600 tokens,
  80-token overlap aligned to a sentence start, hard limit 1,000; prefers
  paragraph, then sentence, then token boundaries; a tail under 120 tokens is
  merged when that stays under the hard limit.
- `Chunk.text == normalized_text[start_offset:end_offset]`. Citation offsets are
  relative to the chunk text (`+ chunk.start_offset` for version offsets).
  Chunks are immutable and content-addressed, so a citation stays resolvable
  after a later parser change (which creates a new version and new chunks).

## Knowledge graph

Ontology `fi-graph-v1` (spec 12.1): Institution, Person, PolicyEvent,
DocumentVersion, Chunk, MacroTopic, MacroSeries, MacroRelease, Instrument;
relationships PUBLISHED_BY, AUTHORED_BY, DOCUMENTS_EVENT, HAS_CHUNK,
MENTIONS_TOPIC, REFERS_TO_SERIES, RELEASE_OF, REFERS_TO_INSTRUMENT, ISSUED_BY,
PREVIOUS_EVENT, SUPERSEDES. Person/Instrument/AUTHORED_BY/ISSUED_BY are defined
but not populated by the current corpus (statements and minutes are Committee
documents; instruments belong to workstream A).

- **Stable ids**: `inst-fomc`, `topic-inflation`, `series-cpi` (FRED `CPIAUCSL`),
  `event-fomc-20230322`, `release-cpi-20230412`, `dv-…`, `chk-…`, `as-…`.
- **Vocabulary** `topic-vocab-v1`, frozen 2022-12-31: 11 topics (inflation,
  inflation expectations, labor market, policy rate, balance sheet, economic
  growth, financial conditions, banking sector, consumer spending, housing,
  foreign economies) and 7 series (CPI, core CPI, PCE price, core PCE,
  unemployment rate, nonfarm payrolls, real GDP).
- **Aliases** are versioned rows with `available_at`. Resolution is exact over
  normalized terms, latest alias version visible at the cutoff, greedy longest
  match. A surface form mapping to several entities (e.g. `PCE`) goes to the
  review queue; there is no fuzzy matching and no merge on name similarity.
  Examples of later aliases: `recalibration` (2024-09-18), `SVB` (2023-03-12).
- **Deterministic relationships** (`metadata_v1`, `event_series_v1`):
  PUBLISHED_BY, DOCUMENTS_EVENT (one PolicyEvent per meeting), HAS_CHUNK,
  PREVIOUS_EVENT, SUPERSEDES.
- **Rule extraction** `rule_lexicon_v1`: explicit-mention regexes per topic and
  series with up to three exact support spans (chunk offsets + quote). Ambiguous
  patterns (bare `PCE` without `price`) produce `review_required` assertions,
  which retrieval never traverses. `confidence` is a review aid only.
- **Releases** `release_fixture_v1`: 24 CPI release dates (2023–2024) from the
  BLS archive → MacroRelease nodes and RELEASE_OF (CPI, core CPI).
- **Availability inheritance**: every assertion's `available_at` is the latest
  `available_at` of all its inputs (subject, object, support).
- **Epistemic boundary** (12.2): no holdings, cash, orders, weights or risk
  numbers in nodes (enforced by property-key check); no causal relationship type.

Each extraction is an `ExtractionRun` per primary input (one document version,
the meeting table, or the release fixture), so runs stay stable as the corpus
grows. `model`/`prompt_version` are null because no model is used.

### Graph backends

`GraphStore` protocol: `begin_build`, `write`, `validate`, `publish`, `fail`,
`status`, `membership`, `node`, `edges(node, steps, cutoff)`, `drop`.

- `InMemoryGraphStore` (default, deterministic). Process-local, so `load_index`
  rebuilds the graph from canonical records and requires the recorded
  assertion-set hash and node count before publishing it again.
- `Neo4jGraphStore`: Python is the only writer; only the parameterized Cypher
  templates in `TEMPLATES` can run; every node/relationship carries `build_id`;
  reads require the `FiBuild` node to be `READY`, which is set only after
  membership and content validation. Typed relations are stored as
  `FI_ASSERTION {relation}` relationships (types cannot be parameterized).
  Start it with `docker compose --profile graph up -d neo4j` (image pinned to
  `neo4j:5.26-community`, loopback ports) and use `--graph neo4j` with
  `NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD`. Integration tests:
  `pytest -m integration tests/evidence` (skipped without `NEO4J_URI`).

**Rebuild and rollback** (15.4): `fi-research index validate` rebuilds the
graph from canonical records into a fresh backend and compares node/assertion
membership and content with the loaded build. Old builds are never mutated;
rolling back means activating an earlier READY build id
(`store.activate_index`, history in `index_activations`).

## Index builds

`build_index` records an `IndexBuild` (BUILDING) with exact member version ids,
chunk-set hash, tokenizer/chunker/normalizer versions, embedding provider/model/
dimensions/matrix hash, index text template, graph schema/backend, extraction
versions and assertion-set hash. It then checks: members active, chunk text
hashes, token limit, every member has chunks, embedding shape/finite/
reproducible, graph membership, graph content hash, availability inheritance.
Only if all pass is the graph published and the build marked READY; any
exception marks it FAILED (tests inject failures at every stage). Identical
members and configuration reuse the same build id. Member versions advance to
`indexed`, and to `active` when the build is activated.

The default build excludes the synthetic correction (`include_synthetic=False`).

## Retrieval

`RetrievalRequest`: question, `decision_as_of`, universe ids, source scope,
mode (`none`, `hybrid_rag_v1`, `graph_rag_v1`), index build id, explicit
identifiers, permission scope, budget.

1. **Eligible snapshot**: member versions in scope, ACTIVE, `available_at <=
   cutoff`, not superseded by another eligible version. Exclusions are
   recorded with reasons (`not_available_at_cutoff`, `superseded_by:…`, …).
2. **Query** (`question+frozen-topic-vocab+identifiers-v1`): question terms +
   expansion terms of topics/series recognised through time-filtered aliases +
   label terms of explicit identifiers (meeting dates). No LLM expansion.
3. **Lexical**: BM25 (k1 1.2, b 0.75) over `title + headings + text`, with N,
   df and average length computed from the snapshot only (6.3). Top 30.
4. **Vector**: exact cosine over snapshot chunks only (no ANN index with future
   members). Top 30. Provider `hash-embed-v1`: signed feature hashing of the
   set of normalized unigrams and bigrams into 1,024 integer buckets. **It is a
   lexical-semantic baseline, not a neural embedding model**: it captures term
   and phrase overlap, not synonymy. Integer vectors make scores exact and
   machine-independent. A real provider plugs in through `EmbeddingProvider`
   and is recorded in the build (a change creates a new build).
5. **Fusion**: reciprocal rank fusion, `k = 60` (configurable), equal weights.
6. **Selection** (`dedupe-diversity-budget-graphquota-v1`): exact-text dedupe,
   same-version overlap dedupe (≥ 50% of the shorter chunk), at most 4 chunks per
   document, at most 12 chunks and 8,000 tokens; greedy in fused order (a later
   smaller chunk may still fit). Truncated candidates are listed.
7. **Persistence**: every run and bundle is stored. The cache key covers
   cutoff, snapshot id, build id, embedding model, algorithm versions, the full
   request and permission scope; the run id derives from it, so repeating a
   request returns the stored run. Records are immutable (a changed algorithm
   under an unchanged version string raises `ImmutableRecordConflict`).

### Graph-assisted retrieval (`graph_rag_v1`)

Same hybrid candidates, plus:

- **Seeds (≤ 8)**: question entities via time-filtered aliases and explicit
  identifiers (relevance 1.0), then policy events of the top hybrid candidates
  (relevance ≤ 0.5 from frozen fused scores). Seeds unavailable at the cutoff
  are excluded with a reason.
- **Traversal**: approved relationship steps only (`TRAVERSAL_STEPS`), semantic
  depth ≤ 2, fanout ≤ 8 per node, ≤ 40 visited assertions (each counted once),
  only assertions and nodes available at the cutoff and in the snapshot.
  Neighbour order is a stable key — round-robin over relation steps, then
  passage relevance on the snapshot, recency, id — never global degree.
- **Materialization**: reached versions contribute ≤ 2 chunks via HAS_CHUNK,
  preferring chunks co-supported by an approved MENTIONS_TOPIC/REFERS_TO_SERIES
  link to a question topic/series seed (recorded as support). No further
  traversal is opened.
- **Graph score** = seed relevance × 1/path length × status weight ×
  (0.5 + 0.5 × passage relevance) × (1 + co-supporting question seeds). The
  graph list is a third RRF input, and up to `graph_reserved_slots = 4` of the
  12 slots are filled first from the graph ranking (same dedupe/diversity/token
  rules); the budget is unchanged.
- **Provenance** per graph passage: seed, path assertion ids, support spans,
  availability checks (all must pass), graph score, ranking contribution and
  `added_by_graph` (not among the hybrid candidates). RELEASE_OF assertions
  reached are returned as `structured_facts` (no passage text).
- **Failure**: a missing, non-READY or failing graph raises
  `GraphRetrievalUnavailable`. Hybrid mode on the same index still works, but
  the graph competitor must report the failure (spec 13.3, 15.3).

### Evidence bundle

Each delivered chunk carries text, text hash, offsets, heading path, document
version, source URL, title, `published_at`, `available_at`, availability
policy, fidelity flags (`current_web_version_not_archived_original` or the
synthetic label), and provenance (channels, ranks, per-channel RRF
contribution, fused score, final rank, graph provenance). Token totals and the
list of budget-truncated chunks are included.

## Citation validation helpers

`validate_citation(citation, bundle, store)` returns `ValidationResult`s for
`citation_membership` (chunk delivered in that bundle), `citation_version`,
`temporal` (chunk available at the bundle cutoff), `stored_text_integrity`
(delivered text equals stored normalized text and hash) and `quote_offsets`
(exact substring and/or offsets; no fuzzy matching). Semantic support is out
of scope here (spec 13.2 step 6 is a separate, reviewed classifier).

## Benchmark (`benchmarks/evidence/`)

- `questions_v1.json` (`evidence-benchmark-v1`): 60 questions — 20 direct
  document, 20 multi-document/event, 20 relationship/revision/temporal/
  insufficient-evidence — each with `decisionAsOf`, expected chunk and version
  ids, forbidden (future) versions, expected CPI release fact where relevant,
  acceptable/required abstention, and adjudication notes. Dev/held-out is fixed
  (alternating within each category, 10/10).
- Expected evidence is auto-annotated by recorded rules (document + heading +
  regex on the version eligible at the cutoff). Manual adjudication is pending
  and offline. Regenerate with `fi-research benchmark build` (deterministic).
- `fi-research benchmark run --split dev|heldout|all [--output …]` reports
  recall/precision at K (all delivered) and at 5, version recall, temporal
  violations, citation id/span validity, graph-added passages and their hits,
  helped/harmed questions (graph vs hybrid recall), release-fact hits and
  latency. Manual factual-support review and abstention quality are reported as
  offline/manual, not computed.
- `results/v1-all.json` is a development run over all 60 questions. Its
  `trial_note` records that the co-support rule and the graph quota were
  finalized after inspecting those results, so its held-out numbers are not
  untouched held-out results (spec 16.1). At that run: hybrid recall@K 0.71,
  graph 0.77 (7 questions helped, 0 harmed); zero temporal violations and 100%
  valid citations in both modes. The previous-meeting labor-market questions
  (C06–C09) fail in both modes: the lexical baseline ranks generic minutes
  sections above the targeted participants' discussion.
- `results/v1-{all,dev,heldout}-2026-11-10.json` re-run the same settings per
  split (same index; reproduces the values above). Report:
  [reports/evidence-benchmark.md](reports/evidence-benchmark.md).

## Persistence and migrations

Tables (schema `research` on SQL Server): `schema_version`, `sources`,
`source_fetch_runs`, `documents`, `document_versions`, `chunks`, `entities`,
`entity_aliases`, `relationship_assertions`, `extraction_runs`,
`index_builds`, `index_build_members`, `index_activations`, `retrieval_runs`,
`evidence_bundles`, `ingestion_items`, `ingestion_attempts`. Key columns are
indexed; `payload` is the canonical JSON of the contract.

Migration path: `ResearchStore.create()` creates the schema if needed, reads
`max(schema_version.version)` and applies each `(version, description, fn)` in
`store.MIGRATIONS` above it in one transaction, recording a row per migration.
To evolve the schema, append a new numbered function (never edit an applied
one); new canonical columns are additive and records stay immutable. The
SQL Server path uses the same SQLAlchemy Core definitions (`UnicodeText` →
`NVARCHAR(MAX)`) and has not been run against a live SQL Server in this
workstream.

## Known limitations

- `hash-embed-v1` is not semantic; paraphrase questions underperform. Swap in a
  real provider (new build) before measured AI runs.
- Fixtures are current web versions, not archived originals (flagged).
- The rule lexicon misses implicit mentions and can over-match broad terms
  (`housing`, `growth`); `Person`/`AUTHORED_BY`/`Instrument` are not populated.
- Graph traversal reads per-node edge lists; fine for this corpus, not tuned
  for large graphs (Neo4j caps a single expansion at 2,000 rows before fanout).
- The SQL Server and Neo4j paths are implemented but only exercised by
  integration tests that need those services.
