# ADR 0005 — Deterministic local embedding and in-memory graph by default; Neo4j optional

- **Status:** Accepted
- **Date:** 2026-11-06
- **Spec:** §5.4, §12, §21 (Neo4j edition, embedding model)

## Context

The spec proposes one Neo4j deployment for graph, vector and lexical indexes. Offline development,
CI and the recorded demo must run without network, credentials or a database server, and historical
retrieval must not use future corpus statistics.

## Decision

- Embeddings: `hash-embed-v1`, a deterministic local hashed bag-of-words embedding. It is not
  semantic; it makes vector ranking reproducible and offline.
- Retrieval scores the eligible snapshot exactly (BM25 + exact vector + reciprocal-rank fusion) with
  statistics computed on the eligible corpus at the cutoff.
- Graph: `InMemoryGraphStore` is the default backend. `Neo4jGraphStore` (driver `neo4j==5.28.8`,
  compose image `neo4j:5.26-community` under `--profile graph`) implements the same interface.
- Index builds are rebuildable from canonical records and only become READY after validation;
  activation is explicit and reversible.

## Consequences

- The Neo4j path is implemented and covered by `integration`-marked tests but has **not** been run
  against a live server in this delivery. Treat it as untested until it is.
- Paraphrase-style questions underperform with `hash-embed-v1`; a real embedding provider is a new
  index build and a new experiment trial.
