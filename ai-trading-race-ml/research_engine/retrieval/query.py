"""Deterministic query construction (spec 12.3 step 2). No LLM expansion.

``question+frozen-topic-vocab+identifiers-v1``:

* question terms (``lex-norm-v1``);
* expansion terms of topics/series recognised in the question through the
  time-filtered alias table (frozen ``topic-vocab-v1`` vocabulary);
* label terms of explicit identifiers (request ``explicit_identifiers`` plus
  policy events/releases recognised in the question), e.g. meeting dates.
"""

from __future__ import annotations

from datetime import datetime

from research_engine.contracts.evidence import NodeType, QuerySpec, RetrievalRequest
from research_engine.evidence.textnorm import lexical_terms
from research_engine.knowledge.resolver import Resolution
from research_engine.knowledge.vocabulary import VOCAB_BY_ID

from .index import EvidenceIndex

QUERY_CONSTRUCTION = "question+frozen-topic-vocab+identifiers-v1"
_GENERIC_LABEL_TERMS = {"fomc", "meeting", "release", "published", "cpi"}
_TOPIC_TYPES = {NodeType.MACRO_TOPIC, NodeType.MACRO_SERIES}
_IDENTIFIER_TYPES = {NodeType.POLICY_EVENT, NodeType.MACRO_RELEASE}


def _identifier_label(index: EvidenceIndex, identifier: str, cutoff: datetime) -> str:
    entity = index.entities.get(identifier)
    if entity is not None and entity.available_at <= cutoff:
        return entity.canonical_name
    version = index.versions.get(identifier)
    if version is not None and version.available_at <= cutoff:
        return version.title
    for version in index.versions.values():
        if version.document_id == identifier and version.available_at <= cutoff:
            return version.title
    return ""


def build_query(
    request: RetrievalRequest, index: EvidenceIndex, resolution: Resolution
) -> QuerySpec:
    cutoff = request.decision_as_of
    terms: list[str] = []

    def add(items: list[str]) -> None:
        for item in items:
            if item not in terms:
                terms.append(item)

    add(lexical_terms(request.question))
    topic_ids: list[str] = []
    topic_terms: list[str] = []
    identifiers: list[str] = list(dict.fromkeys(request.explicit_identifiers))
    for match in resolution.matches:
        if match.entity_type in _TOPIC_TYPES and match.entity_id not in topic_ids:
            topic_ids.append(match.entity_id)
            entry = VOCAB_BY_ID.get(match.entity_id)
            for term in entry.expansion_terms if entry else ():
                folded = lexical_terms(term)
                for f in folded:
                    if f not in topic_terms:
                        topic_terms.append(f)
        elif match.entity_type in _IDENTIFIER_TYPES and match.entity_id not in identifiers:
            identifiers.append(match.entity_id)
    add(topic_terms)
    id_terms: list[str] = []
    for identifier in identifiers:
        for term in lexical_terms(_identifier_label(index, identifier, cutoff)):
            if term not in _GENERIC_LABEL_TERMS and term not in id_terms:
                id_terms.append(term)
    add(id_terms)
    text = request.question
    if topic_terms:
        text += " | topics: " + " ".join(topic_terms)
    if id_terms:
        text += " | identifiers: " + " ".join(id_terms)
    return QuerySpec(
        text=text,
        terms=terms,
        topic_terms=topic_terms,
        topic_entity_ids=topic_ids,
        identifiers=identifiers,
        construction=QUERY_CONSTRUCTION,
    )
