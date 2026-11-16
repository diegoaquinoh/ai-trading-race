# Evidence fixtures (workstream B)

| Path | Content |
|---|---|
| `raw/fed-fomc/calendar/fomccalendars.htm` | FOMC meeting calendar page (discovery and minutes release dates) |
| `raw/fed-fomc/statements/monetary2023MMDDa.htm` … | 16 FOMC policy statements, 2023-02-01 to 2024-12-18 |
| `raw/fed-fomc/minutes/fomcminutes2023MMDD.htm` … | 16 FOMC minutes for the same meetings |
| `raw/MANIFEST.json` | URL, final URL, SHA-256, size, fetch time, `Last-Modified` per file |
| `synthetic/` | One clearly labelled **synthetic** correction of the 2023-03-22 statement (see below) |
| `macro_releases.json` | CPI news-release dates 2023–2024 (dates only) for `MacroRelease` nodes |

## Provenance and rights

- Raw pages were fetched once, sequentially with a 1.5 s delay, from
  `https://www.federalreserve.gov` only (allowlisted host, redirects validated),
  on 2026-11-05 by `research_engine.evidence.fed.fetch_fixtures`.
- They are works of the U.S. federal government (Board of Governors of the
  Federal Reserve System) and are in the public domain in the United States.
  CPI release dates come from the U.S. Bureau of Labor Statistics archive page
  (also a federal work); only the dates are stored.
- **Fidelity flag `current_web_version_not_archived_original`:** these are the
  pages as served in 2026 (their `Last-Modified` headers are 2026 dates), not
  archived copies of the original releases. Every `DocumentVersion` built from
  them carries that flag, and nothing claims byte identity with the original
  publication. Publication times are reconstructed (statement: 14:00
  America/New_York on the final meeting day, confirmed by the page's own
  "For release at 2:00 p.m." line; minutes: 14:00 on the calendar's release date).

## Integrity

`fi-research ingest fed --offline` verifies every file against `MANIFEST.json`
before use; `research_engine.evidence.fed.verify_fixtures()` returns mismatches.
Never edit raw files in place: a changed remote page is a new fixture set.

## Synthetic correction

`synthetic/monetary20230322a-synthetic-correction.htm` is generated from the
real 2023-03-22 statement by the edits listed in `synthetic/corrections.json`
(a visible "SYNTHETIC TEST CORRECTION FIXTURE" banner plus one revised sentence).
It is **not a Federal Reserve publication**. It is ingested only with
`--include-synthetic` (tests and the evidence benchmark), as a version that
`SUPERSEDES` the original and becomes available on 2023-03-29 16:00 America/New_York.
Default agent indexes exclude it.
