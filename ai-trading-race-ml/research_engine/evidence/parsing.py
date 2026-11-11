"""HTML and PDF normalization into offset-mapped text (spec 11.1, 11.2).

Normalized text layout (``normalized-text-v1``):

* Blocks (headings, paragraphs, block quotes, list items, tables) are separated
  by one blank line (``"\\n\\n"``).
* ``<br>`` inside a block becomes a single ``"\\n"``; every other whitespace run
  collapses to one space. Zero-width format characters (U+200B-U+200D, U+2060,
  U+FEFF) are removed. Text is Unicode NFC; other characters are kept.
* Each block records its character span in the normalized text and a locator
  back to the original source (HTML line/column from the parser, or PDF page).

Citations and chunk offsets always refer to this stored normalized text, so they
remain resolvable after a later parser update (which creates a new version).
"""

from __future__ import annotations

import re
import unicodedata
import zlib
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

from research_engine.contracts.evidence import BlockSpan

HTML_PARSER_VERSION = "html-bs4-v1"
PDF_PARSER_VERSION = "pdf-minimal-v1"
NORMALIZED_TEXT_VERSION = "normalized-text-v1"

_BR = " "  # internal sentinel for <br>
_WS = re.compile(r"[ \t\r\n\f\v    ]+")
_BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre", "dd", "dt", "table"}
_HEADING_TAGS = {"h1": 1, "h2": 1, "h3": 1, "h4": 2, "h5": 3, "h6": 3}
_DATE_LINE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|"
    r"December)\b[\w\s,\-–—]*\d{4}$"
)


class ParseError(ValueError):
    """Unparseable input; ``quarantine`` marks documents that must not be retried."""

    def __init__(self, message: str, *, quarantine: bool = False):
        super().__init__(message)
        self.quarantine = quarantine


@dataclass(frozen=True)
class RawBlock:
    kind: str  # "heading" | "paragraph"
    level: int
    text: str
    locator: str


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    text: str
    blocks: tuple[BlockSpan, ...]
    parser_version: str
    media_type: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HtmlParseConfig:
    content_selectors: tuple[str, ...]
    title_selector: Optional[str] = None
    drop_selectors: tuple[str, ...] = ("script", "style", "noscript")
    metadata_selectors: tuple[tuple[str, str], ...] = ()
    strong_lead_headings: bool = False
    strong_heading_max_chars: int = 100
    strong_heading_min_remainder: int = 40


_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))


def normalize_inline(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_ZERO_WIDTH)
    lines = [(_WS.sub(" ", line)).strip() for line in text.split(_BR)]
    return "\n".join(line for line in lines if line)


def assemble(blocks: list[RawBlock]) -> tuple[str, tuple[BlockSpan, ...]]:
    parts: list[str] = []
    spans: list[BlockSpan] = []
    cursor = 0
    for block in blocks:
        if not block.text:
            continue
        if parts:
            parts.append("\n\n")
            cursor += 2
        start = cursor
        parts.append(block.text)
        cursor += len(block.text)
        spans.append(
            BlockSpan(
                kind=block.kind,  # type: ignore[arg-type]
                level=block.level,
                start_offset=start,
                end_offset=cursor,
                source_locator=block.locator,
            )
        )
    return "".join(parts), tuple(spans)


def _locator(tag: Tag) -> str:
    line = getattr(tag, "sourceline", None)
    col = getattr(tag, "sourcepos", None)
    return f"html:line={line},col={col},tag={tag.name}"


def _table_text(table: Tag) -> str:
    rows = []
    for row in table.find_all("tr"):
        cells = [normalize_inline(c.get_text("")) for c in row.find_all(["td", "th"])]
        cells = [c.replace("\n", " ") for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    return _BR.join(rows)


def _has_block_children(tag: Tag) -> bool:
    return any(
        isinstance(c, Tag)
        and (c.name in _BLOCK_TAGS or c.name in {"div", "blockquote", "ul", "ol"})
        for c in tag.children
    )


def _strong_lead(p: Tag, config: HtmlParseConfig) -> Optional[tuple[str, str]]:
    first = None
    for child in p.children:
        if isinstance(child, NavigableString) and not child.strip():
            continue
        first = child
        break
    if not isinstance(first, Tag) or first.name not in {"strong", "b"}:
        return None
    heading = normalize_inline(first.get_text(""))
    if not heading or "\n" in heading or len(heading) > config.strong_heading_max_chars:
        return None
    if heading.endswith(":") or _DATE_LINE.match(heading):
        return None
    full = normalize_inline(p.get_text(""))
    if not full.startswith(heading):
        return None
    remainder = full[len(heading) :].strip()
    if remainder and len(remainder) < config.strong_heading_min_remainder:
        return None
    return heading, remainder


def _walk(node: Tag, config: HtmlParseConfig, out: list[RawBlock]) -> None:
    loose: list[str] = []

    def flush() -> None:
        text = normalize_inline("".join(loose))
        loose.clear()
        if text:
            out.append(RawBlock("paragraph", 0, text, _locator(node)))

    for child in node.children:
        if isinstance(child, NavigableString):
            if child.__class__.__name__ in {"Comment", "Doctype", "Declaration"}:
                continue
            loose.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name
        if name in _HEADING_TAGS:
            flush()
            text = normalize_inline(child.get_text("")).replace("\n", " ")
            if text:
                out.append(RawBlock("heading", _HEADING_TAGS[name], text, _locator(child)))
        elif name == "table":
            flush()
            text = normalize_inline(_table_text(child))
            if text:
                out.append(RawBlock("paragraph", 0, text, _locator(child)))
        elif name == "p" and config.strong_lead_headings and _strong_lead(child, config):
            flush()
            heading, remainder = _strong_lead(child, config)  # type: ignore[misc]
            out.append(RawBlock("heading", 2, heading, _locator(child)))
            if remainder:
                out.append(RawBlock("paragraph", 0, remainder, _locator(child)))
        elif name in _BLOCK_TAGS:
            flush()
            text = normalize_inline(child.get_text(""))
            if text:
                out.append(RawBlock("paragraph", 0, text, _locator(child)))
        elif name in {"div", "section", "article", "blockquote", "ul", "ol", "main", "dl"}:
            if _has_block_children(child) or name in {"ul", "ol", "dl"}:
                flush()
                _walk(child, config, out)
            else:
                flush()
                text = normalize_inline(child.get_text(""))
                if text:
                    out.append(RawBlock("paragraph", 0, text, _locator(child)))
        elif name == "hr":
            flush()
        else:  # inline element
            loose.append(child.get_text(""))
    flush()


def parse_html(raw: bytes, config: HtmlParseConfig) -> ParsedDocument:
    soup = BeautifulSoup(raw, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with(_BR)
    for selector in config.drop_selectors:
        for tag in soup.select(selector):
            tag.decompose()
    metadata: dict[str, str] = {}
    for name, selector in config.metadata_selectors:
        found = soup.select_one(selector)
        if found is not None:
            metadata[name] = normalize_inline(found.get_text("")).replace("\n", " ")
            found.decompose()
    blocks: list[RawBlock] = []
    title = ""
    if config.title_selector:
        title_tag = soup.select_one(config.title_selector)
        if title_tag is not None:
            title = normalize_inline(title_tag.get_text("")).replace("\n", " ")
            blocks.append(RawBlock("heading", 1, title, _locator(title_tag)))
            title_tag.decompose()
    roots: list[Tag] = []
    for selector in config.content_selectors:
        roots.extend(soup.select(selector))
    if not roots:
        raise ParseError("content root not found", quarantine=False)
    for root in roots:
        _walk(root, config, blocks)
    if not title:
        heads = [b for b in blocks if b.kind == "heading"]
        title = heads[0].text if heads else ""
    text, spans = assemble(blocks)
    if len(re.findall(r"[A-Za-z]", text)) < 40:
        raise ParseError("no extractable text in content root", quarantine=True)
    return ParsedDocument(
        title=title,
        text=text,
        blocks=spans,
        parser_version=HTML_PARSER_VERSION,
        media_type="text/html",
        metadata=metadata,
    )


# --------------------------------------------------------------------------- #
# PDF adapter (no OCR): text-layer extraction or quarantine
# --------------------------------------------------------------------------- #

_STREAM = re.compile(rb"<<(?P<dict>.*?)>>\s*stream\r?\n(?P<body>.*?)\r?\nendstream", re.S)
_TEXT_OP = re.compile(
    rb"\((?P<s>(?:\\.|[^\\)])*)\)\s*(?:Tj|'|\")|\[(?P<a>[^\]]*)\]\s*TJ|(?P<et>ET)"
)
_ARRAY_STR = re.compile(rb"\(((?:\\.|[^\\)])*)\)")
_ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def _pdf_unescape(raw: bytes) -> str:
    out = bytearray()
    i = 0
    while i < len(raw):
        ch = raw[i : i + 1]
        if ch == b"\\" and i + 1 < len(raw):
            nxt = raw[i + 1 : i + 2]
            if nxt in _ESC:
                out += _ESC[nxt]
                i += 2
                continue
            octal = re.match(rb"[0-7]{1,3}", raw[i + 1 : i + 4])
            if octal:
                out.append(int(octal.group(0), 8) & 0xFF)
                i += 1 + len(octal.group(0))
                continue
            out += nxt
            i += 2
            continue
        out += ch
        i += 1
    return out.decode("latin-1")


def parse_pdf(raw: bytes, *, title: str = "") -> ParsedDocument:
    """Extract the PDF text layer from Tj/TJ operators; quarantine when empty.

    Scanned/image-only PDFs, encrypted files and unsupported encodings yield no
    extractable text and raise ``ParseError(quarantine=True)``: OCR is out of
    scope initially (spec 11.1), and the quarantine is a visible coverage gap.
    """
    if not raw.startswith(b"%PDF"):
        raise ParseError("not a PDF file", quarantine=True)
    if b"/Encrypt" in raw:
        raise ParseError("encrypted PDF", quarantine=True)
    pages: list[str] = []
    for match in _STREAM.finditer(raw):
        meta, body = match.group("dict"), match.group("body")
        if b"/Image" in meta:
            continue
        if b"/FlateDecode" in meta:
            try:
                body = zlib.decompress(body)
            except zlib.error:
                continue
        elif b"/Filter" in meta:
            continue  # unsupported filter
        lines: list[str] = []
        current: list[str] = []
        for op in _TEXT_OP.finditer(body):
            if op.group("et"):
                if current:
                    lines.append("".join(current))
                    current = []
            elif op.group("s") is not None:
                current.append(_pdf_unescape(op.group("s")))
            else:
                current.extend(_pdf_unescape(s) for s in _ARRAY_STR.findall(op.group("a")))
        if current:
            lines.append("".join(current))
        if lines:
            pages.append(_BR.join(lines))
    blocks = [
        RawBlock("paragraph", 0, normalize_inline(page), f"pdf:stream={index + 1}")
        for index, page in enumerate(pages)
    ]
    text, spans = assemble(blocks)
    if len(re.findall(r"[A-Za-z]", text)) < 40:
        raise ParseError("no extractable text layer (OCR disabled)", quarantine=True)
    return ParsedDocument(
        title=title,
        text=text,
        blocks=spans,
        parser_version=PDF_PARSER_VERSION,
        media_type="application/pdf",
    )
