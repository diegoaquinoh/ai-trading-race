"""Research-owned canonical store (SQLAlchemy Core; spec 5.4, 11.2, 14.7).

* Default: a SQLite file. SQL Server: pass a SQLAlchemy URL such as
  ``mssql+pyodbc://...``; tables are created in schema ``research``.
* ``create()`` is idempotent and records ``schema_version``. Migrations are
  numbered functions in ``MIGRATIONS``; ``create()`` applies those above the
  stored version inside a transaction (documented in
  ``docs/fixed-income/evidence-and-retrieval.md``).
* Each record keeps a few indexed key columns plus ``payload``: the canonical
  JSON of the contract. Canonical records are immutable: re-inserting the same
  payload is a no-op, a different payload under the same id raises
  ``ImmutableRecordConflict``. Exceptions: ``sources.health`` (operational
  status), ``index_builds.status`` (BUILDING -> READY | FAILED only) and the
  ingestion item state machine.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence, TypeVar

import sqlalchemy as sa
from pydantic import BaseModel

from research_engine.contracts.common import canonical_json
from research_engine.contracts.evidence import (
    Chunk,
    Document,
    DocumentVersion,
    Entity,
    EntityAlias,
    EvidenceBundle,
    ExtractionRun,
    IndexBuild,
    IndexBuildStatus,
    IngestionAttempt,
    IngestionState,
    RelationshipAssertion,
    RetrievalRun,
    Source,
    SourceFetchRun,
    SourceHealth,
)

CURRENT_SCHEMA_VERSION = 1
SQLSERVER_SCHEMA = "research"

M = TypeVar("M", bound=BaseModel)


class ImmutableRecordConflict(RuntimeError):
    pass


class InvalidStateTransition(RuntimeError):
    pass


def _epoch(value: Optional[datetime]) -> Optional[int]:
    if value is None:
        return None
    return int(value.astimezone(timezone.utc).timestamp())


def _payload(model: BaseModel) -> str:
    return canonical_json(model.model_dump(mode="json", by_alias=True))


def _id(n: int = 200) -> sa.Unicode:
    return sa.Unicode(n)


def build_metadata(schema: Optional[str]) -> sa.MetaData:
    md = sa.MetaData(schema=schema)
    sa.Table(
        "schema_version",
        md,
        sa.Column("version", sa.Integer, primary_key=True),
        sa.Column("description", _id(400), nullable=False),
        sa.Column("applied_at", _id(40), nullable=False),
    )
    sa.Table(
        "sources",
        md,
        sa.Column("source_id", _id(), primary_key=True),
        sa.Column("payload", sa.UnicodeText, nullable=False),
        sa.Column("health", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "source_fetch_runs",
        md,
        sa.Column("fetch_run_id", _id(), primary_key=True),
        sa.Column("source_id", _id(), nullable=False, index=True),
        sa.Column("started_epoch", sa.BigInteger, nullable=False),
        sa.Column("outcome", _id(40), nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "documents",
        md,
        sa.Column("document_id", _id(), primary_key=True),
        sa.Column("source_id", _id(), nullable=False, index=True),
        sa.Column("document_type", _id(60), nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "document_versions",
        md,
        sa.Column("version_id", _id(), primary_key=True),
        sa.Column("document_id", _id(), nullable=False, index=True),
        sa.Column("source_id", _id(), nullable=False),
        sa.Column("content_hash", _id(80), nullable=False),
        sa.Column("normalized_text_hash", _id(80), nullable=False),
        sa.Column("available_epoch", sa.BigInteger, nullable=False, index=True),
        sa.Column("status", _id(40), nullable=False),
        sa.Column("supersedes", _id(), nullable=True),
        sa.Column("synthetic", sa.Boolean, nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "chunks",
        md,
        sa.Column("chunk_id", _id(), primary_key=True),
        sa.Column("version_id", _id(), nullable=False, index=True),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("text_hash", _id(80), nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "entities",
        md,
        sa.Column("entity_id", _id(), primary_key=True),
        sa.Column("entity_type", _id(60), nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "entity_aliases",
        md,
        sa.Column("alias_id", _id(), primary_key=True),
        sa.Column("entity_id", _id(), nullable=False, index=True),
        sa.Column("normalized_alias", _id(400), nullable=False, index=True),
        sa.Column("available_epoch", sa.BigInteger, nullable=False),
        sa.Column("status", _id(40), nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "relationship_assertions",
        md,
        sa.Column("assertion_id", _id(), primary_key=True),
        sa.Column("relation", _id(60), nullable=False, index=True),
        sa.Column("subject_id", _id(), nullable=False, index=True),
        sa.Column("object_id", _id(), nullable=False, index=True),
        sa.Column("available_epoch", sa.BigInteger, nullable=False),
        sa.Column("validation_status", _id(40), nullable=False),
        sa.Column("extraction_run_id", _id(), nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "extraction_runs",
        md,
        sa.Column("extraction_run_id", _id(), primary_key=True),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "index_builds",
        md,
        sa.Column("build_id", _id(), primary_key=True),
        sa.Column("status", _id(20), nullable=False),
        sa.Column("created_epoch", sa.BigInteger, nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "index_build_members",
        md,
        sa.Column("build_id", _id(), primary_key=True),
        sa.Column("version_id", _id(), primary_key=True),
    )
    sa.Table(
        "index_activations",
        md,
        sa.Column("activation_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("build_id", _id(), nullable=False),
        sa.Column("activated_at", _id(40), nullable=False),
    )
    sa.Table(
        "retrieval_runs",
        md,
        sa.Column("retrieval_run_id", _id(), primary_key=True),
        sa.Column("cache_key", _id(80), nullable=False, index=True),
        sa.Column("build_id", _id(), nullable=False),
        sa.Column("cutoff_epoch", sa.BigInteger, nullable=False),
        sa.Column("generated_at", _id(40), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "evidence_bundles",
        md,
        sa.Column("bundle_id", _id(), primary_key=True),
        sa.Column("retrieval_run_id", _id(), nullable=False, index=True),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    sa.Table(
        "ingestion_items",
        md,
        sa.Column("source_id", _id(), primary_key=True),
        sa.Column("document_id", _id(), primary_key=True),
        sa.Column("state", _id(40), nullable=False),
        sa.Column("version_id", _id(), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("updated_at", _id(40), nullable=False),
    )
    sa.Table(
        "ingestion_attempts",
        md,
        sa.Column("attempt_id", _id(), primary_key=True),
        sa.Column("source_id", _id(), nullable=False, index=True),
        sa.Column("document_id", _id(), nullable=False, index=True),
        sa.Column("attempted_at", _id(40), nullable=False),
        sa.Column("payload", sa.UnicodeText, nullable=False),
    )
    return md


def _migration_1(conn: sa.Connection, md: sa.MetaData) -> None:
    md.create_all(conn, checkfirst=True)


# Append (version, description, fn) to evolve the schema. Never edit applied ones.
MIGRATIONS: list[tuple[int, str, Callable[[sa.Connection, sa.MetaData], None]]] = [
    (1, "initial research evidence schema", _migration_1),
]


class ResearchStore:
    """Canonical research records. Python is the sole writer."""

    def __init__(self, url: str, *, echo: bool = False):
        self.url = url
        self.engine = sa.create_engine(url, echo=echo, future=True)
        self.dialect = self.engine.dialect.name
        self.schema = SQLSERVER_SCHEMA if self.dialect == "mssql" else None
        self.md = build_metadata(self.schema)
        self.t = self.md.tables
        self._prefix = f"{self.schema}." if self.schema else ""

    @classmethod
    def sqlite(cls, path: Path | str) -> "ResearchStore":
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        store = cls(f"sqlite:///{path}")
        store.create()
        return store

    @classmethod
    def memory(cls) -> "ResearchStore":
        store = cls("sqlite+pysqlite:///:memory:")
        store.create()
        return store

    def tbl(self, name: str) -> sa.Table:
        return self.t[self._prefix + name]

    # ------------------------------------------------------------------ schema
    def create(self) -> int:
        with self.engine.begin() as conn:
            if self.dialect == "mssql":
                conn.execute(
                    sa.text(
                        "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = :s) "
                        "EXEC('CREATE SCHEMA research')"
                    ),
                    {"s": SQLSERVER_SCHEMA},
                )
            self.tbl("schema_version").create(conn, checkfirst=True)
            current = conn.execute(
                sa.select(sa.func.max(self.tbl("schema_version").c.version))
            ).scalar()
            current = int(current or 0)
            for version, description, fn in MIGRATIONS:
                if version <= current:
                    continue
                fn(conn, self.md)
                conn.execute(
                    self.tbl("schema_version").insert(),
                    {
                        "version": version,
                        "description": description,
                        "applied_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                current = version
        return current

    def schema_version(self) -> int:
        with self.engine.connect() as conn:
            value = conn.execute(
                sa.select(sa.func.max(self.tbl("schema_version").c.version))
            ).scalar()
        return int(value or 0)

    # --------------------------------------------------------------- generic
    def _insert_immutable(
        self, table: str, pk: str, rows: Sequence[dict[str, Any]], conn: sa.Connection
    ) -> int:
        if not rows:
            return 0
        tbl = self.tbl(table)
        ids = [r[pk] for r in rows]
        existing: dict[str, str] = {}
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            for row in conn.execute(
                sa.select(tbl.c[pk], tbl.c.payload).where(tbl.c[pk].in_(batch))
            ):
                existing[row[0]] = row[1]
        new_rows = []
        seen: set[str] = set()
        for row in rows:
            key = row[pk]
            if key in existing:
                if existing[key] != row["payload"]:
                    raise ImmutableRecordConflict(
                        f"{table}.{key} already stored with other content"
                    )
                continue
            if key in seen:
                continue
            seen.add(key)
            new_rows.append(row)
        if new_rows:
            conn.execute(tbl.insert(), new_rows)
        return len(new_rows)

    def _get(self, table: str, pk: str, key: str, model: type[M]) -> Optional[M]:
        tbl = self.tbl(table)
        with self.engine.connect() as conn:
            payload = conn.execute(sa.select(tbl.c.payload).where(tbl.c[pk] == key)).scalar()
        return None if payload is None else model.model_validate(json.loads(payload))

    def _list(
        self, table: str, model: type[M], where: Optional[Any] = None, order: Any = None
    ) -> list[M]:
        tbl = self.tbl(table)
        query = sa.select(tbl.c.payload)
        if where is not None:
            query = query.where(where(tbl.c) if callable(where) else where)
        if order is not None:
            query = query.order_by(*(order(tbl.c) if callable(order) else order))
        with self.engine.connect() as conn:
            return [model.model_validate(json.loads(row[0])) for row in conn.execute(query)]

    # --------------------------------------------------------------- sources
    def upsert_source(self, source: Source) -> None:
        tbl = self.tbl("sources")
        config = source.model_copy(update={"health": SourceHealth()})
        payload = _payload(config)
        with self.engine.begin() as conn:
            row = conn.execute(
                sa.select(tbl.c.payload, tbl.c.health).where(tbl.c.source_id == source.source_id)
            ).first()
            if row is None:
                conn.execute(
                    tbl.insert(),
                    {
                        "source_id": source.source_id,
                        "payload": payload,
                        "health": _payload(source.health),
                    },
                )
            elif row[0] != payload:
                # Registry configuration changes are explicit replacements; health is kept.
                conn.execute(
                    tbl.update().where(tbl.c.source_id == source.source_id).values(payload=payload)
                )

    def get_source(self, source_id: str) -> Optional[Source]:
        tbl = self.tbl("sources")
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(tbl.c.payload, tbl.c.health).where(tbl.c.source_id == source_id)
            ).first()
        if row is None:
            return None
        data = json.loads(row[0])
        data["health"] = json.loads(row[1])
        return Source.model_validate(data)

    def set_source_health(self, source_id: str, health: SourceHealth) -> None:
        tbl = self.tbl("sources")
        with self.engine.begin() as conn:
            conn.execute(
                tbl.update().where(tbl.c.source_id == source_id).values(health=_payload(health))
            )

    def add_fetch_run(self, run: SourceFetchRun) -> None:
        with self.engine.begin() as conn:
            self._insert_immutable(
                "source_fetch_runs",
                "fetch_run_id",
                [
                    {
                        "fetch_run_id": run.fetch_run_id,
                        "source_id": run.source_id,
                        "started_epoch": _epoch(run.started_at),
                        "outcome": run.outcome.value,
                        "payload": _payload(run),
                    }
                ],
                conn,
            )

    def list_fetch_runs(self, source_id: str) -> list[SourceFetchRun]:
        return self._list(
            "source_fetch_runs",
            SourceFetchRun,
            where=lambda c: c.source_id == source_id,
            order=lambda c: (c.started_epoch, c.fetch_run_id),
        )

    # ------------------------------------------------------------- documents
    def put_document(self, document: Document) -> bool:
        with self.engine.begin() as conn:
            return bool(
                self._insert_immutable(
                    "documents",
                    "document_id",
                    [
                        {
                            "document_id": document.document_id,
                            "source_id": document.source_id,
                            "document_type": document.document_type.value,
                            "payload": _payload(document),
                        }
                    ],
                    conn,
                )
            )

    def get_document(self, document_id: str) -> Optional[Document]:
        return self._get("documents", "document_id", document_id, Document)

    def list_documents(self, source_id: Optional[str] = None) -> list[Document]:
        where = (lambda c: c.source_id == source_id) if source_id else None
        return self._list("documents", Document, where=where, order=lambda c: (c.document_id,))

    def put_version(self, version: DocumentVersion) -> bool:
        with self.engine.begin() as conn:
            return bool(
                self._insert_immutable(
                    "document_versions",
                    "version_id",
                    [
                        {
                            "version_id": version.version_id,
                            "document_id": version.document_id,
                            "source_id": version.source_id,
                            "content_hash": version.content_hash,
                            "normalized_text_hash": version.normalized_text_hash,
                            "available_epoch": _epoch(version.available_at),
                            "status": version.status.value,
                            "supersedes": version.supersedes,
                            "synthetic": version.synthetic,
                            "payload": _payload(version),
                        }
                    ],
                    conn,
                )
            )

    def get_version(self, version_id: str) -> Optional[DocumentVersion]:
        return self._get("document_versions", "version_id", version_id, DocumentVersion)

    def list_versions(
        self, document_id: Optional[str] = None, include_synthetic: bool = True
    ) -> list[DocumentVersion]:
        def where(c: Any) -> Any:
            clauses = []
            if document_id:
                clauses.append(c.document_id == document_id)
            if not include_synthetic:
                clauses.append(c.synthetic == sa.false())
            return sa.and_(sa.true(), *clauses)

        return self._list(
            "document_versions",
            DocumentVersion,
            where=where,
            order=lambda c: (c.available_epoch, c.version_id),
        )

    def find_version(
        self, document_id: str, normalized_text_hash: str, parser_version: str
    ) -> Optional[DocumentVersion]:
        for version in self.list_versions(document_id):
            if (
                version.normalized_text_hash == normalized_text_hash
                and version.parser_version == parser_version
            ):
                return version
        return None

    # ---------------------------------------------------------------- chunks
    def put_chunks(self, chunks: Iterable[Chunk]) -> int:
        rows = [
            {
                "chunk_id": c.chunk_id,
                "version_id": c.version_id,
                "ordinal": c.ordinal,
                "text_hash": c.text_hash,
                "token_count": c.token_count,
                "payload": _payload(c),
            }
            for c in chunks
        ]
        with self.engine.begin() as conn:
            return self._insert_immutable("chunks", "chunk_id", rows, conn)

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        return self._get("chunks", "chunk_id", chunk_id, Chunk)

    def chunks_for_versions(self, version_ids: Iterable[str]) -> list[Chunk]:
        ids = sorted(set(version_ids))
        out: list[Chunk] = []
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            out.extend(
                self._list(
                    "chunks",
                    Chunk,
                    where=lambda c, b=batch: c.version_id.in_(b),
                    order=lambda c: (c.version_id, c.ordinal),
                )
            )
        out.sort(key=lambda c: (c.version_id, c.ordinal))
        return out

    # ------------------------------------------------------------- knowledge
    def put_entities(self, entities: Iterable[Entity]) -> int:
        rows = [
            {
                "entity_id": e.entity_id,
                "entity_type": e.entity_type.value,
                "payload": _payload(e),
            }
            for e in entities
        ]
        with self.engine.begin() as conn:
            return self._insert_immutable("entities", "entity_id", rows, conn)

    def list_entities(self) -> list[Entity]:
        return self._list("entities", Entity, order=lambda c: (c.entity_id,))

    def put_aliases(self, aliases: Iterable[EntityAlias]) -> int:
        rows = [
            {
                "alias_id": a.alias_id,
                "entity_id": a.entity_id,
                "normalized_alias": a.normalized_alias,
                "available_epoch": _epoch(a.available_at),
                "status": a.status.value,
                "payload": _payload(a),
            }
            for a in aliases
        ]
        with self.engine.begin() as conn:
            return self._insert_immutable("entity_aliases", "alias_id", rows, conn)

    def list_aliases(self) -> list[EntityAlias]:
        return self._list("entity_aliases", EntityAlias, order=lambda c: (c.alias_id,))

    def put_assertions(self, assertions: Iterable[RelationshipAssertion]) -> int:
        rows = [
            {
                "assertion_id": a.assertion_id,
                "relation": a.relation.value,
                "subject_id": a.subject_id,
                "object_id": a.object_id,
                "available_epoch": _epoch(a.available_at),
                "validation_status": a.validation_status.value,
                "extraction_run_id": a.extraction_run_id,
                "payload": _payload(a),
            }
            for a in assertions
        ]
        with self.engine.begin() as conn:
            return self._insert_immutable("relationship_assertions", "assertion_id", rows, conn)

    def list_assertions(self) -> list[RelationshipAssertion]:
        return self._list(
            "relationship_assertions", RelationshipAssertion, order=lambda c: (c.assertion_id,)
        )

    def put_extraction_run(self, run: ExtractionRun) -> bool:
        with self.engine.begin() as conn:
            return bool(
                self._insert_immutable(
                    "extraction_runs",
                    "extraction_run_id",
                    [{"extraction_run_id": run.extraction_run_id, "payload": _payload(run)}],
                    conn,
                )
            )

    def list_extraction_runs(self) -> list[ExtractionRun]:
        return self._list("extraction_runs", ExtractionRun, order=lambda c: (c.extraction_run_id,))

    # ---------------------------------------------------------- index builds
    def put_index_build(self, build: IndexBuild) -> None:
        if build.status != IndexBuildStatus.BUILDING:
            raise InvalidStateTransition("new index builds must start as BUILDING")
        with self.engine.begin() as conn:
            self._insert_immutable(
                "index_builds",
                "build_id",
                [
                    {
                        "build_id": build.build_id,
                        "status": build.status.value,
                        "created_epoch": _epoch(build.created_at),
                        "payload": _payload(build),
                    }
                ],
                conn,
            )
            members = self.tbl("index_build_members")
            have = {
                r[0]
                for r in conn.execute(
                    sa.select(members.c.version_id).where(members.c.build_id == build.build_id)
                )
            }
            rows = [
                {"build_id": build.build_id, "version_id": v}
                for v in build.member_version_ids
                if v not in have
            ]
            if rows:
                conn.execute(members.insert(), rows)

    def update_index_build(self, build: IndexBuild) -> None:
        """Only BUILDING -> READY | FAILED; membership and config are immutable."""
        tbl = self.tbl("index_builds")
        with self.engine.begin() as conn:
            row = conn.execute(
                sa.select(tbl.c.status, tbl.c.payload).where(tbl.c.build_id == build.build_id)
            ).first()
            if row is None:
                raise KeyError(build.build_id)
            if row[0] != IndexBuildStatus.BUILDING.value:
                raise InvalidStateTransition(f"build {build.build_id} is already {row[0]}")
            stored = IndexBuild.model_validate(json.loads(row[1]))
            frozen = {"status", "validated_at", "validation_checks", "error"}
            if stored.model_dump(exclude=frozen) != build.model_dump(exclude=frozen):
                raise ImmutableRecordConflict("index build configuration/membership is immutable")
            conn.execute(
                tbl.update()
                .where(tbl.c.build_id == build.build_id)
                .values(status=build.status.value, payload=_payload(build))
            )

    def get_index_build(self, build_id: str) -> Optional[IndexBuild]:
        return self._get("index_builds", "build_id", build_id, IndexBuild)

    def list_index_builds(self) -> list[IndexBuild]:
        return self._list("index_builds", IndexBuild, order=lambda c: (c.created_epoch, c.build_id))

    def index_members(self, build_id: str) -> list[str]:
        members = self.tbl("index_build_members")
        with self.engine.connect() as conn:
            return sorted(
                r[0]
                for r in conn.execute(
                    sa.select(members.c.version_id).where(members.c.build_id == build_id)
                )
            )

    def activate_index(self, build_id: str, at: datetime) -> None:
        build = self.get_index_build(build_id)
        if build is None or build.status != IndexBuildStatus.READY:
            raise InvalidStateTransition("only READY builds can be activated")
        with self.engine.begin() as conn:
            conn.execute(
                self.tbl("index_activations").insert(),
                {"build_id": build_id, "activated_at": at.astimezone(timezone.utc).isoformat()},
            )

    def active_index_id(self) -> Optional[str]:
        tbl = self.tbl("index_activations")
        with self.engine.connect() as conn:
            return conn.execute(
                sa.select(tbl.c.build_id).order_by(tbl.c.activation_id.desc()).limit(1)
            ).scalar()

    # ------------------------------------------------------------- retrieval
    def _immutable_write(self, write: Callable[[sa.Connection], Any], attempts: int = 3) -> Any:
        """Run an immutable-insert transaction, tolerating concurrent identical writers.

        ``_insert_immutable`` checks for existing rows and then inserts, so two writers
        persisting the same content-addressed record at once (e.g. two strategies issuing
        an identical retrieval) can both pass the check; the loser gets an IntegrityError.
        Retrying is correct: the retry sees the committed row and verifies its payload is
        identical (raising ImmutableRecordConflict otherwise).
        """
        for attempt in range(1, attempts + 1):
            try:
                with self.engine.begin() as conn:
                    return write(conn)
            except sa.exc.IntegrityError:
                if attempt == attempts:
                    raise

    def put_retrieval(
        self, run: RetrievalRun, bundle: EvidenceBundle, generated_at: datetime, duration_ms: int
    ) -> bool:
        return bool(
            self._immutable_write(
                lambda conn: self._put_retrieval_rows(run, bundle, generated_at, duration_ms, conn)
            )
        )

    def _put_retrieval_rows(
        self,
        run: RetrievalRun,
        bundle: EvidenceBundle,
        generated_at: datetime,
        duration_ms: int,
        conn: sa.Connection,
    ) -> int:
        inserted = self._insert_immutable(
            "retrieval_runs",
            "retrieval_run_id",
            [
                {
                    "retrieval_run_id": run.retrieval_run_id,
                    "cache_key": run.cache_key,
                    "build_id": run.index_build_id,
                    "cutoff_epoch": _epoch(run.cutoff),
                    "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
                    "duration_ms": duration_ms,
                    "payload": _payload(run),
                }
            ],
            conn,
        )
        self._insert_immutable(
            "evidence_bundles",
            "bundle_id",
            [
                {
                    "bundle_id": bundle.bundle_id,
                    "retrieval_run_id": bundle.retrieval_run_id,
                    "payload": _payload(bundle),
                }
            ],
            conn,
        )
        return inserted

    def get_retrieval_run(self, run_id: str) -> Optional[RetrievalRun]:
        return self._get("retrieval_runs", "retrieval_run_id", run_id, RetrievalRun)

    def find_retrieval_by_cache_key(self, cache_key: str) -> Optional[RetrievalRun]:
        runs = self._list("retrieval_runs", RetrievalRun, where=lambda c: c.cache_key == cache_key)
        return runs[0] if runs else None

    def get_bundle(self, bundle_id: str) -> Optional[EvidenceBundle]:
        return self._get("evidence_bundles", "bundle_id", bundle_id, EvidenceBundle)

    # ------------------------------------------------------------- ingestion
    def item_state(
        self, source_id: str, document_id: str
    ) -> Optional[tuple[IngestionState, Optional[str], int]]:
        tbl = self.tbl("ingestion_items")
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(tbl.c.state, tbl.c.version_id, tbl.c.attempts).where(
                    (tbl.c.source_id == source_id) & (tbl.c.document_id == document_id)
                )
            ).first()
        if row is None:
            return None
        return IngestionState(row[0]), row[1], int(row[2])

    def list_item_states(self, source_id: str) -> dict[str, tuple[IngestionState, Optional[str]]]:
        tbl = self.tbl("ingestion_items")
        with self.engine.connect() as conn:
            rows = conn.execute(
                sa.select(tbl.c.document_id, tbl.c.state, tbl.c.version_id).where(
                    tbl.c.source_id == source_id
                )
            ).all()
        return {r[0]: (IngestionState(r[1]), r[2]) for r in rows}

    def record_attempt(
        self, attempt: IngestionAttempt, *, update_state: bool = True, bump_attempts: bool = False
    ) -> None:
        items = self.tbl("ingestion_items")
        with self.engine.begin() as conn:
            self._insert_immutable(
                "ingestion_attempts",
                "attempt_id",
                [
                    {
                        "attempt_id": attempt.attempt_id,
                        "source_id": attempt.source_id,
                        "document_id": attempt.document_id,
                        "attempted_at": attempt.attempted_at.isoformat(),
                        "payload": _payload(attempt),
                    }
                ],
                conn,
            )
            if not update_state:
                return
            row = conn.execute(
                sa.select(items.c.attempts).where(
                    (items.c.source_id == attempt.source_id)
                    & (items.c.document_id == attempt.document_id)
                )
            ).first()
            values = {
                "state": attempt.to_state.value,
                "version_id": attempt.version_id,
                "updated_at": attempt.attempted_at.isoformat(),
            }
            if row is None:
                conn.execute(
                    items.insert(),
                    {
                        "source_id": attempt.source_id,
                        "document_id": attempt.document_id,
                        "attempts": 1 if bump_attempts else 0,
                        **values,
                    },
                )
            else:
                if bump_attempts:
                    values["attempts"] = int(row[0]) + 1
                if attempt.version_id is None:
                    values.pop("version_id")
                conn.execute(
                    items.update()
                    .where(
                        (items.c.source_id == attempt.source_id)
                        & (items.c.document_id == attempt.document_id)
                    )
                    .values(**values)
                )

    def list_attempts(self, source_id: Optional[str] = None) -> list[IngestionAttempt]:
        where = (lambda c: c.source_id == source_id) if source_id else None
        return self._list(
            "ingestion_attempts",
            IngestionAttempt,
            where=where,
            order=lambda c: (c.attempted_at, c.attempt_id),
        )
