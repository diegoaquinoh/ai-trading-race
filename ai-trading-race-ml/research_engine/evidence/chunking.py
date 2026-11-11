"""Pinned tokenizer and section-based chunker (spec 11.3).

Tokenizer ``ws-regex-v1``: a token is a maximal run of word characters with
internal apostrophes, hyphens, slashes or periods between word characters
(``5-1/4``, ``Committee's``, ``U.S``), or a single non-space, non-word character.
It is a counting/segmentation tokenizer for budgets, not a model tokenizer; a
provider tokenizer can count differently, so budgets are declared in these units.

Chunker ``section-v1``:

* Never crosses a section (heading) boundary or a document version.
* Targets 600 tokens with 80-token overlap and a hard limit of 1,000 tokens.
* Prefers paragraph boundaries, then sentence boundaries, then a token boundary.
* Chunk text is always an exact slice of the stored normalized text, so
  ``text == normalized[start_offset:end_offset]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from research_engine.contracts.evidence import BlockSpan

TOKENIZER_VERSION = "ws-regex-v1"
CHUNKER_VERSION = "section-v1"
TARGET_TOKENS = 600
OVERLAP_TOKENS = 80
HARD_MAX_TOKENS = 1000
MIN_TAIL_TOKENS = 120

_TOKEN = re.compile(r"\w+(?:['’./\-]\w+)*|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class Token:
    start: int
    end: int


def tokenize_spans(text: str, offset: int = 0) -> list[Token]:
    return [Token(m.start() + offset, m.end() + offset) for m in _TOKEN.finditer(text)]


def count_tokens(text: str) -> int:
    return sum(1 for _ in _TOKEN.finditer(text))


@dataclass(frozen=True)
class ChunkSpan:
    heading_path: tuple[str, ...]
    start: int
    end: int
    token_count: int


@dataclass(frozen=True)
class _Section:
    heading_path: tuple[str, ...]
    start: int
    end: int
    paragraph_starts: tuple[int, ...]


def _sections(text: str, blocks: tuple[BlockSpan, ...] | list[BlockSpan]) -> list[_Section]:
    sections: list[_Section] = []
    path: list[tuple[int, str]] = []
    current_start: int | None = None
    current_path: tuple[str, ...] = ()
    paragraph_starts: list[int] = []
    last_end = 0

    def close() -> None:
        if current_start is not None and last_end > current_start:
            sections.append(
                _Section(current_path, current_start, last_end, tuple(paragraph_starts))
            )

    for block in blocks:
        if block.kind == "heading":
            close()
            heading = text[block.start_offset : block.end_offset]
            level = max(block.level, 1)
            path = [p for p in path if p[0] < level] + [(level, heading)]
            current_path = tuple(h for _, h in path)
            current_start = block.start_offset
            paragraph_starts = [block.start_offset]
        else:
            if current_start is None:
                current_start = block.start_offset
                current_path = tuple(h for _, h in path)
                paragraph_starts = []
            paragraph_starts.append(block.start_offset)
        last_end = block.end_offset
    close()
    return sections


def _sentence_starts(text: str, tokens: list[Token]) -> set[int]:
    """Token indices that start a sentence (after ., ?, ! or a newline)."""
    starts = {0}
    for index in range(1, len(tokens)):
        prev = text[tokens[index - 1].start : tokens[index - 1].end]
        gap = text[tokens[index - 1].end : tokens[index].start]
        if prev in {".", "?", "!"} or "\n" in gap:
            starts.add(index)
    return starts


def chunk_section(text: str, section: _Section) -> list[ChunkSpan]:
    tokens = tokenize_spans(text[section.start : section.end], section.start)
    n = len(tokens)
    if n == 0:
        return []
    para_index = {i for i, t in enumerate(tokens) if t.start in set(section.paragraph_starts)}
    sentence_index = _sentence_starts(text, tokens)
    out: list[ChunkSpan] = []
    pos = 0
    while pos < n:
        remaining = n - pos
        if remaining <= TARGET_TOKENS or (
            remaining <= HARD_MAX_TOKENS and remaining - TARGET_TOKENS < MIN_TAIL_TOKENS
        ):
            end = n
        else:
            lo = pos + TARGET_TOKENS // 2
            hi = min(pos + HARD_MAX_TOKENS, n)
            target = pos + TARGET_TOKENS

            def best(candidates: set[int]) -> int | None:
                valid = [c for c in candidates if lo <= c <= hi and c < n]
                if not valid:
                    return None
                return min(valid, key=lambda c: (abs(c - target), c))

            end = best(para_index) or best(sentence_index) or min(target, n)
            if n - end < MIN_TAIL_TOKENS and n - pos <= HARD_MAX_TOKENS:
                end = n
        start_char = tokens[pos].start
        end_char = tokens[end - 1].end
        out.append(ChunkSpan(section.heading_path, start_char, end_char, end - pos))
        if end >= n:
            break
        next_pos = max(end - OVERLAP_TOKENS, pos + 1)
        aligned = [i for i in sentence_index if next_pos <= i < end]
        pos = min(aligned) if aligned else next_pos
    return out


def chunk_document(text: str, blocks: tuple[BlockSpan, ...] | list[BlockSpan]) -> list[ChunkSpan]:
    spans: list[ChunkSpan] = []
    for section in _sections(text, blocks):
        spans.extend(chunk_section(text, section))
    for span in spans:
        if span.token_count > HARD_MAX_TOKENS:
            raise AssertionError("chunk exceeds hard token limit")
    return spans
