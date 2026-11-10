"""Evidence, knowledge-graph and retrieval contracts (spec 6, 11, 12, 13.2-13.3).

Records here are research-owned (SQL schema ``research``). Python is the only
writer. Every record that enters a hash is float-free: scores and confidences
are decimal strings with fixed precision (``SCORE_PLACES`` decimal places).

Time fields follow spec 6.1: ``published_at`` (source made it public),
``available_at`` (earliest permitted use under the declared information policy),
``ingested_at`` (platform obtained the bytes), ``decision_as_of`` (strict cutoff).
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .common import (
    ContentHash,
    ContractModel,
    DecimalStr,
    OpaqueId,
    SourceId,
    UtcDatetime,
)
from .decisions import RetrievalMode

EVIDENCE_SCHEMA_VERSION = "1.0"
SCORE_PLACES = 10
_SCORE_QUANTUM = Decimal(1).scaleb(-SCORE_PLACES)


def score_decimal(value: float | int | Decimal) -> Decimal:
    """Convert a numeric score to a fixed-precision Decimal for hashed contracts.

    Python float formatting of a given IEEE double is deterministic, so the
    intermediate ``repr`` is reproducible; quantization hides last-bit noise.
    """
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, int):
        dec = Decimal(value)
    else:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite score")
        dec = Decimal(repr(float(value)))
    out = dec.quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_EVEN)
    if out == 0:  # normalize -0
        return Decimal(0).quantize(_SCORE_QUANTUM)
    return out


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class DocumentType(str, Enum):
    FOMC_STATEMENT = "fomc_statement"
    FOMC_MINUTES = "fomc_minutes"


class DiscoveryMethod(str, Enum):
    PINNED_URL_LIST = "pinned_url_list"
    CALENDAR_PAGE = "calendar_page"
    PINNED_LIST_VALIDATED_BY_CALENDAR = "pinned_list_validated_by_calendar"


class SourceHealthStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # partial failures in the last run
    OUTAGE = "outage"  # the last run could not reach the source
    STALE = "stale"  # no successful refresh within the freshness expectation


class VersionStatus(str, Enum):
    ACTIVE = "active"  # eligible for indexing (subject to available_at)
    QUARANTINED = "quarantined"  # unreadable / no extractable text (no OCR)
    REVIEW_REQUIRED = "review_required"
    WITHDRAWN = "withdrawn"


class IngestionState(str, Enum):
    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    PARSED = "parsed"
    CHUNKED = "chunked"
    EXTRACTED = "extracted"
    INDEXED = "indexed"
    ACTIVE = "active"
    FAILED_RETRYABLE = "failed_retryable"
    QUARANTINED = "quarantined"
    REVIEW_REQUIRED = "review_required"


class FetchRunOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    OUTAGE = "outage"


class NodeType(str, Enum):
    """Ontology node types (spec 12.1)."""

    INSTITUTION = "Institution"
    PERSON = "Person"
    POLICY_EVENT = "PolicyEvent"
    DOCUMENT_VERSION = "DocumentVersion"
    CHUNK = "Chunk"
    MACRO_TOPIC = "MacroTopic"
    MACRO_SERIES = "MacroSeries"
    MACRO_RELEASE = "MacroRelease"
    INSTRUMENT = "Instrument"


class RelationType(str, Enum):
    """Ontology relationship types (spec 12.1)."""

    PUBLISHED_BY = "PUBLISHED_BY"
    AUTHORED_BY = "AUTHORED_BY"
    DOCUMENTS_EVENT = "DOCUMENTS_EVENT"
    HAS_CHUNK = "HAS_CHUNK"
    MENTIONS_TOPIC = "MENTIONS_TOPIC"
    REFERS_TO_SERIES = "REFERS_TO_SERIES"
    RELEASE_OF = "RELEASE_OF"
    REFERS_TO_INSTRUMENT = "REFERS_TO_INSTRUMENT"
    ISSUED_BY = "ISSUED_BY"
    PREVIOUS_EVENT = "PREVIOUS_EVENT"
    SUPERSEDES = "SUPERSEDES"


class AssertionStatus(str, Enum):
    APPROVED = "approved"  # deterministic metadata or approved-lexicon match
    REVIEW_REQUIRED = "review_required"  # never traversed by retrieval
    REJECTED = "rejected"


class AliasStatus(str, Enum):
    APPROVED = "approved"
    REVIEW_REQUIRED = "review_required"
    RETIRED = "retired"


class IndexBuildStatus(str, Enum):
    BUILDING = "BUILDING"
    READY = "READY"
    FAILED = "FAILED"


class RetrievalChannel(str, Enum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    GRAPH = "graph"


# --------------------------------------------------------------------------- #
# Source registry and ingestion
# --------------------------------------------------------------------------- #


class RetryPolicy(ContractModel):
    max_attempts: int = 3
    backoff_seconds: list[int] = Field(default_factory=lambda: [2, 10, 30])
    request_timeout_seconds: int = 30
    politeness_delay_ms: int = 1500


class SourceHealth(ContractModel):
    status: SourceHealthStatus = SourceHealthStatus.UNKNOWN
    last_attempt_at: Optional[UtcDatetime] = None
    last_success_at: Optional[UtcDatetime] = None  # only advanced by a successful refresh
    last_outcome: Optional[FetchRunOutcome] = None
    consecutive_failures: int = 0
    last_error: Optional[str] = None


class Source(ContractModel):
    """Source registry entry (spec 11.1)."""

    source_id: SourceId
    name: str
    owner: str
    publisher_entity_id: OpaqueId
    allowed_hosts: list[str]
    discovery_method: DiscoveryMethod
    discovery_urls: list[str] = Field(default_factory=list)
    document_types: list[DocumentType]
    expected_cadence: str  # human-readable, e.g. "8 scheduled meetings per year"
    parser_version: str
    adapter_version: str
    timestamp_rule: str  # declared rule id for published_at / available_at
    availability_policy: str
    availability_lag_minutes: int
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    freshness_expectation_hours: int
    license_note: str
    health: SourceHealth = Field(default_factory=SourceHealth)


class SourceFetchRun(ContractModel):
    """One refresh attempt of a whole source. Outages are recorded, never hidden."""

    fetch_run_id: OpaqueId
    source_id: SourceId
    started_at: UtcDatetime
    completed_at: UtcDatetime
    outcome: FetchRunOutcome
    mode: Literal["online", "offline_fixture"]
    # When source content was actually observed: fetch completion online, the
    # fixture capture time offline. Only this advances freshness, never wall time.
    source_observed_at: Optional[UtcDatetime] = None
    items_discovered: int = 0
    items_new_versions: int = 0
    items_unchanged: int = 0
    items_failed: int = 0
    error: Optional[str] = None


class IngestionAttempt(ContractModel):
    """One state-machine transition attempt for one document item (spec 11.3)."""

    attempt_id: OpaqueId
    source_id: SourceId
    document_id: OpaqueId
    fetch_run_id: Optional[OpaqueId] = None
    stage: str
    from_state: Optional[IngestionState] = None
    to_state: IngestionState
    outcome: Literal["ok", "failed", "skipped_unchanged"]
    attempt_number: int = 1
    attempted_at: UtcDatetime
    version_id: Optional[OpaqueId] = None
    artifact_hash: Optional[ContentHash] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Canonical documents
# --------------------------------------------------------------------------- #


class Document(ContractModel):
    document_id: OpaqueId
    source_id: SourceId
    document_type: DocumentType
    canonical_url: str
    publisher_entity_id: OpaqueId
    event_id: Optional[OpaqueId] = None  # PolicyEvent the document documents
    source_native_id: str


class BlockSpan(ContractModel):
    """Map from a normalized-text block to its original HTML/PDF location."""

    kind: Literal["heading", "paragraph"]
    level: int = 0
    start_offset: int
    end_offset: int
    source_locator: str  # e.g. "html:line=812,col=3,tag=p" or "pdf:page=2"


class DocumentVersion(ContractModel):
    version_id: OpaqueId
    document_id: OpaqueId
    source_id: SourceId
    document_type: DocumentType
    content_hash: ContentHash  # SHA-256 of the raw source bytes first seen
    normalized_text_hash: ContentHash
    title: str
    language: str = "en"
    source_url: str
    published_at: UtcDatetime
    published_at_precision: Literal["minute", "date"]
    publication_timezone: str = "America/New_York"
    publication_time_basis: str  # what established published_at
    available_at: UtcDatetime
    availability_policy: str
    ingested_at: UtcDatetime
    raw_artifact_uri: str
    normalized_artifact_uri: str
    media_type: str
    parser_version: str
    status: VersionStatus
    supersedes: Optional[OpaqueId] = None  # correction replaces an earlier version
    fidelity_flags: list[str] = Field(default_factory=list)
    synthetic: bool = False
    event_id: Optional[OpaqueId] = None
    char_count: int
    blocks: list[BlockSpan] = Field(default_factory=list)

    @model_validator(mode="after")
    def _chronology(self) -> "DocumentVersion":
        if self.available_at < self.published_at:
            raise ValueError("available_at cannot precede published_at")
        return self


class Chunk(ContractModel):
    chunk_id: OpaqueId
    version_id: OpaqueId
    document_id: OpaqueId
    heading_path: list[str]
    ordinal: int
    text: str  # exact normalized text == normalized_document[start_offset:end_offset]
    text_hash: ContentHash
    start_offset: int
    end_offset: int
    token_count: int
    tokenizer_version: str
    chunker_version: str
    available_at: UtcDatetime  # inherited from the version

    @model_validator(mode="after")
    def _offsets(self) -> "Chunk":
        if self.end_offset - self.start_offset != len(self.text):
            raise ValueError("chunk offsets do not match text length")
        return self


# --------------------------------------------------------------------------- #
# Knowledge graph records
# --------------------------------------------------------------------------- #


class Entity(ContractModel):
    entity_id: OpaqueId
    entity_type: NodeType
    canonical_name: str
    available_at: UtcDatetime  # when the entity record became admissible
    properties: dict[str, str] = Field(default_factory=dict)
    provenance: str


class EntityAlias(ContractModel):
    """Controlled alias table entry; versioned and time-filtered (spec 12.1)."""

    alias_id: OpaqueId
    entity_id: OpaqueId
    alias: str  # surface form
    normalized_alias: str
    alias_version: int = 1
    available_at: UtcDatetime
    status: AliasStatus = AliasStatus.APPROVED
    provenance: str


class SupportSpan(ContractModel):
    """Exact passage span or structured source row supporting an assertion."""

    kind: Literal["chunk_span", "source_row", "metadata"]
    chunk_id: Optional[OpaqueId] = None
    version_id: Optional[OpaqueId] = None
    start_offset: Optional[int] = None  # offsets into the chunk text
    end_offset: Optional[int] = None
    quote: Optional[str] = None
    source_ref: Optional[str] = None  # e.g. "fixtures/evidence/macro_releases.json#cpi-2023-01"


class RelationshipAssertion(ContractModel):
    assertion_id: OpaqueId
    subject_id: OpaqueId
    subject_type: NodeType
    relation: RelationType
    object_id: OpaqueId
    object_type: NodeType
    support: list[SupportSpan]
    input_ids: list[OpaqueId]  # every record whose availability the assertion inherits
    available_at: UtcDatetime  # latest available_at of all supporting inputs
    extraction_method: str  # "metadata_v1" | "rule_lexicon_v1" | "release_fixture_v1"
    extraction_version: str
    extraction_run_id: OpaqueId
    validation_status: AssertionStatus
    confidence: DecimalStr  # review aid only, not a probability of financial truth


class ExtractionRun(ContractModel):
    extraction_run_id: OpaqueId
    method: str
    method_version: str
    graph_schema_version: str
    model: Optional[str] = None  # no LLM is used by rule extraction
    prompt_version: Optional[str] = None
    input_ids: list[OpaqueId]
    input_hash: ContentHash
    output_hash: ContentHash
    assertion_count: int
    review_count: int = 0
    errors: list[str] = Field(default_factory=list)
    generated_at: UtcDatetime


class GraphNode(ContractModel):
    node_id: OpaqueId
    node_type: NodeType
    label: str
    available_at: UtcDatetime
    properties: dict[str, str] = Field(default_factory=dict)


class IndexBuild(ContractModel):
    """Exact, immutable index manifest. Never READY until validated (spec 11.3)."""

    build_id: OpaqueId
    status: IndexBuildStatus
    member_version_ids: list[OpaqueId]
    member_chunk_count: int
    member_chunk_set_hash: ContentHash
    tokenizer_version: str
    chunker_version: str
    lexical_normalizer_version: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    embedding_matrix_hash: ContentHash  # canonical little-endian matrix bytes
    index_text_template: str
    graph_schema_version: str
    graph_backend: str
    extraction_versions: list[str]
    assertion_count: int
    assertion_set_hash: ContentHash
    node_count: int
    created_at: UtcDatetime
    validated_at: Optional[UtcDatetime] = None
    validation_checks: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    includes_synthetic: bool = False

    @model_validator(mode="after")
    def _ready_requires_validation(self) -> "IndexBuild":
        if self.status == IndexBuildStatus.READY and (
            self.validated_at is None or not self.validation_checks
        ):
            raise ValueError("an index build cannot be READY without recorded validation")
        return self


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #


class RetrievalBudget(ContractModel):
    max_chunks: int = 12
    max_evidence_tokens: int = 8000
    lexical_candidates: int = 30
    vector_candidates: int = 30
    rrf_k: int = 60
    max_chunks_per_document: int = 4
    overlap_dedupe_ratio: DecimalStr = Decimal("0.5")
    graph_max_seeds: int = 8
    graph_max_depth: int = 2
    graph_max_fanout: int = 8
    graph_max_visited_assertions: int = 40
    graph_chunks_per_document: int = 2
    graph_rrf_weight: DecimalStr = Decimal("1")
    # Graph mode only: up to this many of the max_chunks slots are filled first from
    # the graph-ranked list (same dedupe/diversity/token rules); the rest by fused rank.
    graph_reserved_slots: int = 4


class RetrievalRequest(ContractModel):
    schema_version: str = EVIDENCE_SCHEMA_VERSION
    question: str
    decision_as_of: UtcDatetime
    universe_ids: list[OpaqueId] = Field(default_factory=list)
    source_scope: list[SourceId] = Field(default_factory=lambda: ["fed-fomc"])
    mode: RetrievalMode = RetrievalMode.HYBRID_RAG
    index_build_id: OpaqueId
    explicit_identifiers: list[OpaqueId] = Field(default_factory=list)
    permission_scope: str = "public"
    budget: RetrievalBudget = Field(default_factory=RetrievalBudget)


class QuerySpec(ContractModel):
    text: str
    terms: list[str]
    topic_terms: list[str] = Field(default_factory=list)
    topic_entity_ids: list[OpaqueId] = Field(default_factory=list)
    identifiers: list[OpaqueId] = Field(default_factory=list)
    construction: str  # e.g. "question+frozen-topic-vocab+identifiers v1"


class RetrievalCandidate(ContractModel):
    chunk_id: OpaqueId
    version_id: OpaqueId
    document_id: OpaqueId
    channels: list[RetrievalChannel]
    lexical_rank: Optional[int] = None
    lexical_score: Optional[DecimalStr] = None
    vector_rank: Optional[int] = None
    vector_score: Optional[DecimalStr] = None
    graph_rank: Optional[int] = None
    graph_score: Optional[DecimalStr] = None
    fused_score: DecimalStr
    fused_rank: int
    delivered: bool = False


class Exclusion(ContractModel):
    record_id: OpaqueId
    record_type: Literal["chunk", "document_version", "assertion", "seed", "node"]
    reason: str


class AvailabilityCheck(ContractModel):
    record_id: OpaqueId
    record_type: str
    available_at: UtcDatetime
    cutoff: UtcDatetime
    passed: bool


class GraphSeed(ContractModel):
    seed_id: OpaqueId
    seed_type: NodeType
    origin: Literal["question_alias", "explicit_identifier", "candidate_metadata"]
    matched_text: Optional[str] = None
    alias_id: Optional[OpaqueId] = None
    relevance: DecimalStr


class GraphTrace(ContractModel):
    seeds: list[GraphSeed] = Field(default_factory=list)
    visited_assertion_ids: list[OpaqueId] = Field(default_factory=list)
    limits_hit: list[str] = Field(default_factory=list)
    review_queue: list[str] = Field(default_factory=list)  # uncertain alias matches
    graph_backend: str = ""
    graph_build_id: Optional[OpaqueId] = None


class GraphProvenance(ContractModel):
    seed_id: OpaqueId
    path_assertion_ids: list[OpaqueId]
    path_length: int
    support_spans: list[SupportSpan]
    availability_checks: list[AvailabilityCheck]
    graph_score: DecimalStr
    added_by_graph: bool  # not among the hybrid lexical/vector candidates


class ChunkProvenance(ContractModel):
    channels: list[RetrievalChannel]
    lexical_rank: Optional[int] = None
    vector_rank: Optional[int] = None
    graph_rank: Optional[int] = None
    ranking_contribution: dict[str, DecimalStr]  # channel -> fused-score contribution
    fused_score: DecimalStr
    final_rank: int
    graph: Optional[GraphProvenance] = None
    availability_checks: list[AvailabilityCheck] = Field(default_factory=list)


class DeliveredChunk(ContractModel):
    chunk_id: OpaqueId
    version_id: OpaqueId
    document_id: OpaqueId
    source_id: SourceId
    document_type: DocumentType
    title: str
    source_url: str
    published_at: UtcDatetime
    available_at: UtcDatetime
    availability_policy: str
    heading_path: list[str]
    ordinal: int
    start_offset: int
    end_offset: int
    text: str
    text_hash: ContentHash
    token_count: int
    fidelity_flags: list[str] = Field(default_factory=list)
    synthetic: bool = False
    provenance: ChunkProvenance


class StructuredFact(ContractModel):
    """A graph-reached structured assertion (no passage text), e.g. a release date."""

    assertion_id: OpaqueId
    relation: RelationType
    subject_id: OpaqueId
    subject_label: str
    object_id: OpaqueId
    object_label: str
    available_at: UtcDatetime
    support: list[SupportSpan]


class EvidenceBundle(ContractModel):
    schema_version: str = EVIDENCE_SCHEMA_VERSION
    bundle_id: OpaqueId
    retrieval_run_id: OpaqueId
    decision_as_of: UtcDatetime
    mode: RetrievalMode
    index_build_id: OpaqueId
    snapshot_id: OpaqueId
    chunks: list[DeliveredChunk]
    structured_facts: list[StructuredFact] = Field(default_factory=list)
    total_tokens: int
    chunk_count: int
    truncated_by_budget: list[OpaqueId] = Field(default_factory=list)
    empty: bool = False

    def chunk(self, chunk_id: str) -> Optional[DeliveredChunk]:
        for item in self.chunks:
            if item.chunk_id == chunk_id:
                return item
        return None


class RetrievalRun(ContractModel):
    schema_version: str = EVIDENCE_SCHEMA_VERSION
    retrieval_run_id: OpaqueId
    request: RetrievalRequest
    request_hash: ContentHash
    cache_key: ContentHash
    query: QuerySpec
    cutoff: UtcDatetime
    filters: dict[str, str]
    snapshot_id: OpaqueId
    snapshot_version_ids: list[OpaqueId]
    snapshot_chunk_count: int
    index_build_id: OpaqueId
    embedding_model: str
    candidates: list[RetrievalCandidate]
    exclusions: list[Exclusion]
    delivered_chunk_ids: list[OpaqueId]
    bundle_id: OpaqueId
    graph: Optional[GraphTrace] = None
    engine_version: str


# Bundle hash payload helper -------------------------------------------------- #


def bundle_identity_payload(bundle: EvidenceBundle) -> dict:
    wire = bundle.to_wire()
    wire.pop("bundleId", None)
    return wire
