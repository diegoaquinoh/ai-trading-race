"""Time-filtered entity resolution through the controlled alias table (spec 12.1).

* Only approved aliases and entities with ``available_at <= cutoff`` participate.
* For each normalized alias the latest ``alias_version`` visible at the cutoff
  wins; if that version maps to several entities the surface form is
  *ambiguous* and goes to the review queue instead of producing a match.
* Matching is exact over ``lex-norm-v1`` terms (stopwords kept), greedy
  longest-match left to right. There is no fuzzy or similarity matching, so two
  entities are never merged because their names resemble each other.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from research_engine.contracts.evidence import AliasStatus, Entity, EntityAlias, NodeType
from research_engine.evidence.textnorm import alias_key


@dataclass(frozen=True)
class AliasMatch:
    entity_id: str
    entity_type: NodeType
    alias_id: str
    surface: str
    start_term: int
    end_term: int


@dataclass(frozen=True)
class Resolution:
    matches: tuple[AliasMatch, ...]
    review: tuple[str, ...]

    def entity_ids(self) -> list[str]:
        out: list[str] = []
        for match in self.matches:
            if match.entity_id not in out:
                out.append(match.entity_id)
        return out


class AliasResolver:
    def __init__(self, aliases: list[EntityAlias], entities: list[Entity]):
        self._entities = {e.entity_id: e for e in entities}
        self._by_key: dict[tuple[str, ...], list[EntityAlias]] = defaultdict(list)
        for alias in sorted(aliases, key=lambda a: a.alias_id):
            if alias.status != AliasStatus.APPROVED:
                continue
            key = tuple(alias.normalized_alias.split())
            if key:
                self._by_key[key].append(alias)
        self._max_len = max((len(k) for k in self._by_key), default=0)

    def entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def _visible(self, key: tuple[str, ...], cutoff: datetime) -> list[EntityAlias]:
        visible = [
            a
            for a in self._by_key.get(key, [])
            if a.available_at <= cutoff
            and a.entity_id in self._entities
            and self._entities[a.entity_id].available_at <= cutoff
        ]
        if not visible:
            return []
        latest = max(a.alias_version for a in visible)
        return [a for a in visible if a.alias_version == latest]

    def resolve(self, text: str, cutoff: datetime) -> Resolution:
        terms = alias_key(text).split()
        matches: list[AliasMatch] = []
        review: list[str] = []
        i = 0
        while i < len(terms):
            found = False
            for length in range(min(self._max_len, len(terms) - i), 0, -1):
                key = tuple(terms[i : i + length])
                visible = self._visible(key, cutoff)
                if not visible:
                    continue
                entity_ids = sorted({a.entity_id for a in visible})
                surface = " ".join(key)
                if len(entity_ids) > 1:
                    review.append(f"ambiguous alias '{surface}' -> {', '.join(entity_ids)}")
                else:
                    alias = min(visible, key=lambda a: a.alias_id)
                    matches.append(
                        AliasMatch(
                            entity_id=alias.entity_id,
                            entity_type=self._entities[alias.entity_id].entity_type,
                            alias_id=alias.alias_id,
                            surface=surface,
                            start_term=i,
                            end_term=i + length,
                        )
                    )
                i += length
                found = True
                break
            if not found:
                i += 1
        return Resolution(tuple(matches), tuple(review))
