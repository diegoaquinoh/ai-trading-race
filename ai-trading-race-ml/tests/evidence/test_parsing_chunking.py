"""Parsing, offsets, chunking limits, PDF quarantine, Fed adapter timestamps."""

from __future__ import annotations

import zlib
from datetime import datetime, timezone

import pytest

from research_engine.evidence import fed
from research_engine.evidence.chunking import (
    HARD_MAX_TOKENS,
    OVERLAP_TOKENS,
    chunk_document,
    count_tokens,
    tokenize_spans,
)
from research_engine.evidence.parsing import HtmlParseConfig, ParseError, parse_html, parse_pdf


def test_fixture_checksums_match_manifest():
    assert fed.verify_fixtures() == []
    manifest = fed.load_manifest()
    assert len(manifest) == 33  # calendar + 16 statements + 16 minutes
    assert all(e.final_url.startswith("https://www.federalreserve.gov/") for e in manifest.values())


def test_pinned_meetings_match_calendar_fixture():
    raw = (fed.RAW_ROOT / "fed-fomc/calendar/fomccalendars.htm").read_bytes()
    assert fed.validate_against_calendar(fed.parse_calendar(raw)) == []
    assert len(fed.PINNED_MEETINGS) == 16


def test_release_instants_are_dst_aware_and_lagged():
    # 2023-02-01 is EST (UTC-5); 2023-06-14 is EDT (UTC-4).
    assert fed.release_instant(fed.meeting_by_key("20230201").end) == datetime(
        2023, 2, 1, 19, 0, tzinfo=timezone.utc
    )
    june = fed.release_instant(fed.meeting_by_key("20230614").end)
    assert june == datetime(2023, 6, 14, 18, 0, tzinfo=timezone.utc)
    assert (fed.available_instant(june) - june).total_seconds() == 120 * 60


def test_statement_pages_confirm_two_pm_release():
    for spec in fed.document_specs():
        if spec.document_type.value != "fomc_statement":
            continue
        parsed = fed.parse_fed_document((fed.RAW_ROOT / spec.fixture_path).read_bytes(), spec)
        assert fed.statement_release_time_matches(parsed), spec.document_id


def test_html_blocks_map_exactly_to_normalized_text():
    html = (
        b"<html><body><div id='c'><h3>Title</h3><p>First   para<br>line two</p>"
        b"<p><strong>Section A</strong> Body text that is long enough to be a paragraph body.</p>"
        b"<table><tr><td>a</td><td>b</td></tr></table></div></body></html>"
    )
    parsed = parse_html(html, HtmlParseConfig(content_selectors=("#c",), strong_lead_headings=True))
    kinds = [(b.kind, parsed.text[b.start_offset : b.end_offset]) for b in parsed.blocks]
    assert kinds[0] == ("heading", "Title")
    assert kinds[1] == ("paragraph", "First para\nline two")
    assert kinds[2] == ("heading", "Section A")
    assert kinds[-1] == ("paragraph", "a | b")
    assert all(b.source_locator.startswith("html:line=") for b in parsed.blocks)


def test_html_without_text_is_quarantined():
    with pytest.raises(ParseError) as err:
        parse_html(
            b"<div id='c'><img src='x.png'></div>", HtmlParseConfig(content_selectors=("#c",))
        )
    assert err.value.quarantine


def _pdf(content: bytes, compress: bool = True) -> bytes:
    body = zlib.compress(content) if compress else content
    filt = b"/Filter /FlateDecode " if compress else b""
    return (
        b"%PDF-1.4\n1 0 obj\n<< "
        + filt
        + b"/Length "
        + str(len(body)).encode()
        + b" >>\nstream\n"
        + body
        + b"\nendstream\nendobj\n%%EOF"
    )


def test_pdf_text_layer_is_extracted():
    text = (
        b"BT (The Committee decided to maintain the target range for the federal funds rate.) Tj ET"
    )
    parsed = parse_pdf(_pdf(text))
    assert "target range for the federal funds rate" in parsed.text
    assert parsed.blocks[0].source_locator.startswith("pdf:")


def test_pdf_without_text_layer_is_quarantined_not_ocred():
    image_only = b"q 612 0 0 792 0 0 cm /Im1 Do Q"
    with pytest.raises(ParseError) as err:
        parse_pdf(_pdf(image_only))
    assert err.value.quarantine
    with pytest.raises(ParseError):
        parse_pdf(b"not a pdf")


def test_tokenizer_is_pinned():
    assert count_tokens("Committee's 5-1/4 to 5-1/2 percent.") == 6
    spans = tokenize_spans("U.S. rates")
    assert [(s.start, s.end) for s in spans] == [(0, 3), (3, 4), (5, 10)]


@pytest.fixture(scope="module")
def parsed_minutes():
    out = []
    for spec in fed.document_specs():
        parsed = fed.parse_fed_document((fed.RAW_ROOT / spec.fixture_path).read_bytes(), spec)
        out.append((spec, parsed))
    return out


def test_chunks_respect_limits_sections_and_offsets(parsed_minutes):
    for spec, parsed in parsed_minutes:
        spans = chunk_document(parsed.text, parsed.blocks)
        assert spans, spec.document_id
        for span in spans:
            assert 0 < span.token_count <= HARD_MAX_TOKENS
            assert count_tokens(parsed.text[span.start : span.end]) == span.token_count
        # consecutive chunks within a section overlap by at most 80 tokens
        for a, b in zip(spans, spans[1:]):
            if a.heading_path == b.heading_path and b.start < a.end:
                assert count_tokens(parsed.text[b.start : a.end]) <= OVERLAP_TOKENS
            if a.heading_path != b.heading_path:
                assert b.start >= a.end  # never crosses a section boundary


def test_long_section_is_split_with_target_and_overlap():
    paragraph = " ".join(f"word{i}." for i in range(1400))
    text = "Heading\n\n" + paragraph
    from research_engine.contracts.evidence import BlockSpan

    blocks = [
        BlockSpan(kind="heading", level=1, start_offset=0, end_offset=7, source_locator="t"),
        BlockSpan(
            kind="paragraph", level=0, start_offset=9, end_offset=len(text), source_locator="t"
        ),
    ]
    spans = chunk_document(text, blocks)
    assert len(spans) >= 3
    assert all(s.token_count <= HARD_MAX_TOKENS for s in spans)
    assert all(s.heading_path == ("Heading",) for s in spans)
