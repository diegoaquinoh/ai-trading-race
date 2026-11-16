# Evidence comparison - 2024-02-21 fomc_minutes

Event: [Minutes of the Federal Open Market Committee (January 30–31, 2024)](https://www.federalreserve.gov/monetarypolicy/fomcminutes20240131.htm) - published 2024-02-21T19:00:00+00:00, available 2024-02-21T21:00:00+00:00 (reconstructed: publication + 120 min).

AI strategies ran on `reference-heuristic-v1` (deterministic rule-based model, not a hosted LLM).

- RAG delivered 6 passages; Graph RAG delivered 18.
- Common: 4; RAG only: 2; Graph only: 14; added by graph traversal: 0.
- Same decision for RAG and Graph RAG: True.
- Event document (doc-fed-fomc-minutes-20240131) among delivered passages: llm_graph=True, llm_rag=False, llm_team=False.

"Graph only" passages reached llm_graph through its graph-mode retrieval and `expand_evidence_graph` call; "added by graph traversal" counts passages whose provenance says they were not among the hybrid lexical/vector candidates (`addedByGraph=true`).

## llm_rag: completed_hold (HOLD)

| Rank | Chunk | Document | Section | Channels | Graph |
|---|---|---|---|---|---|
| 1 | `chk-e3a40739fc8d7487c322` | doc-fed-fomc-minutes-20231101 | ipants' Views on Current Conditions and the Economic Outlook | lexical, vector |  |
| 2 | `chk-e3c4c00720b1199f0ada` | doc-fed-fomc-minutes-20230614 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector |  |
| 3 | `chk-b4f73f0cfcea8d65133d` | doc-fed-fomc-minutes-20230920 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector |  |
| 4 | `chk-f29ec703be9e992eb639` | doc-fed-fomc-statement-20230614 | Federal Reserve issues FOMC statement | lexical, vector |  |
| 5 | `chk-30730f2817360fa30cd1` | doc-fed-fomc-minutes-20230201 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector |  |
| 6 | `chk-0f0f74b2792d006a221c` | doc-fed-fomc-minutes-20230726 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector |  |

Cited claims:

- [valid] Minutes of the Federal Open Market Committee (September 19-20, 2023) states: In determining the extent of additional policy firming that may be appropriate to return inflation to 2 percent over time, members concurred that they would take into account the cumulative tightening of (`chk-b4f73f0cfcea8d65133d`)
- [valid] Minutes of the Federal Open Market Committee (July 25-26, 2023) states: In support of the Committee's objectives to achieve maximum employment and inflation at the rate of 2 percent over the longer run, members agreed to raise the target range for the federal funds rate to 5-1/4  (`chk-0f0f74b2792d006a221c`)
- [valid] Minutes of the Federal Open Market Committee (June 13–14, 2023) states: In determining the extent of additional policy firming that may be appropriate to return inflation to 2 percent over time, members concurred that they will take into account the cumulative tightening of monet (`chk-e3c4c00720b1199f0ada`)

## llm_graph: completed_hold (HOLD)

| Rank | Chunk | Document | Section | Channels | Graph |
|---|---|---|---|---|---|
| 1 | `chk-d7227563709e6ea41427` | doc-fed-fomc-minutes-20230614 | n Market Committee > Staff Review of the Financial Situation | lexical, vector, graph | seed `topic-inflation`, added=False, 1 assertion(s) |
| 2 | `chk-846fb11cb51a74b8b0fc` | doc-fed-fomc-minutes-20230920 | ipants' Views on Current Conditions and the Economic Outlook | lexical, vector, graph | seed `topic-inflation`, added=False, 1 assertion(s) |
| 3 | `chk-441c3a0aede33f759ba2` | doc-fed-fomc-minutes-20240131 | n Market Committee > Staff Review of the Financial Situation | lexical, vector, graph | seed `topic-inflation`, added=False, 1 assertion(s) |
| 4 | `chk-b3f05dd5896868171e96` | doc-fed-fomc-minutes-20240131 | Developments in Financial Markets and Open Market Operations | lexical, vector, graph | seed `topic-inflation`, added=False, 1 assertion(s) |
| 5 | `chk-b3d2acec621329379677` | doc-fed-fomc-minutes-20230201 | Developments in Financial Markets and Open Market Operations | lexical, vector, graph | seed `topic-inflation`, added=False, 1 assertion(s) |
| 6 | `chk-57a280aedff8c8995232` | doc-fed-fomc-minutes-20230503 | ipants' Views on Current Conditions and the Economic Outlook | lexical, vector, graph | seed `topic-inflation`, added=False, 1 assertion(s) |
| 7 | `chk-720f5b175a704e61a6c3` | doc-fed-fomc-minutes-20230322 | n Market Committee > Staff Review of the Financial Situation | lexical, vector, graph | seed `event-fomc-20230322`, added=False, 3 assertion(s) |
| 8 | `chk-b1719567f24170aa2c52` | doc-fed-fomc-minutes-20230322 | Developments in Financial Markets and Open Market Operations | lexical, vector, graph | seed `event-fomc-20230322`, added=False, 3 assertion(s) |
| 9 | `chk-49ddecef6cd30ac269f3` | doc-fed-fomc-minutes-20231213 | n Market Committee > Staff Review of the Financial Situation | lexical, vector, graph | seed `event-fomc-20231213`, added=False, 3 assertion(s) |
| 10 | `chk-9fa276947b732022300f` | doc-fed-fomc-minutes-20230201 | n Market Committee > Staff Review of the Financial Situation | lexical, vector, graph | seed `event-fomc-20230201`, added=False, 3 assertion(s) |
| 11 | `chk-5e7b8d7a70a7ca8c5786` | doc-fed-fomc-minutes-20230726 | n Market Committee > Staff Review of the Financial Situation | lexical, vector, graph | seed `event-fomc-20230614`, added=False, 4 assertion(s) |
| 12 | `chk-073b31d71abd9650b8c4` | doc-fed-fomc-minutes-20230920 | f the Federal Open Market Committee > Staff Economic Outlook | vector, graph | seed `topic-inflation`, added=False, 1 assertion(s) |
| 1 | `chk-e3a40739fc8d7487c322` | doc-fed-fomc-minutes-20231101 | ipants' Views on Current Conditions and the Economic Outlook | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 2 | `chk-e3c4c00720b1199f0ada` | doc-fed-fomc-minutes-20230614 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 3 | `chk-b4f73f0cfcea8d65133d` | doc-fed-fomc-minutes-20230920 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 4 | `chk-f29ec703be9e992eb639` | doc-fed-fomc-statement-20230614 | Federal Reserve issues FOMC statement | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 5 | `chk-74ba21b0dd1bc613140e` | doc-fed-fomc-minutes-20231213 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 6 | `chk-5e70f3ee1d6971231c31` | doc-fed-fomc-minutes-20231101 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |

Cited claims:

- [valid] Minutes of the Federal Open Market Committee (December 12–13, 2023) states: In determining the extent of any additional policy firming that may be appropriate to return inflation to 2 percent over time, members concurred that they would take into account the cumulative tightening (`chk-74ba21b0dd1bc613140e`)
- [valid] Minutes of the Federal Open Market Committee (October 31–November 1, 2023) states: In determining the extent of additional policy firming that may be appropriate to return inflation to 2 percent over time, members concurred that they would take into account the cumulative tighten (`chk-5e70f3ee1d6971231c31`)
- [valid] Minutes of the Federal Open Market Committee (September 19-20, 2023) states: This information would be valuable in determining the extent of additional policy firming that may be appropriate to return inflation to 2 percent over time. (`chk-846fb11cb51a74b8b0fc`)

## llm_team: completed_hold (HOLD)

| Rank | Chunk | Document | Section | Channels | Graph |
|---|---|---|---|---|---|
| 1 | `chk-e3a40739fc8d7487c322` | doc-fed-fomc-minutes-20231101 | ipants' Views on Current Conditions and the Economic Outlook | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 2 | `chk-e3c4c00720b1199f0ada` | doc-fed-fomc-minutes-20230614 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 3 | `chk-b4f73f0cfcea8d65133d` | doc-fed-fomc-minutes-20230920 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 4 | `chk-f29ec703be9e992eb639` | doc-fed-fomc-statement-20230614 | Federal Reserve issues FOMC statement | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 5 | `chk-74ba21b0dd1bc613140e` | doc-fed-fomc-minutes-20231213 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |
| 6 | `chk-5e70f3ee1d6971231c31` | doc-fed-fomc-minutes-20231101 | the Federal Open Market Committee > Committee Policy Actions | lexical, vector, graph | seed `topic-inflation`, added=False, 3 assertion(s) |

Cited claims:

- [valid] Minutes of the Federal Open Market Committee (December 12–13, 2023) states: In determining the extent of any additional policy firming that may be appropriate to return inflation to 2 percent over time, members concurred that they would take into account the cumulative tightening (`chk-74ba21b0dd1bc613140e`)
- [valid] Minutes of the Federal Open Market Committee (October 31–November 1, 2023) states: In determining the extent of additional policy firming that may be appropriate to return inflation to 2 percent over time, members concurred that they would take into account the cumulative tighten (`chk-5e70f3ee1d6971231c31`)
- [valid] Minutes of the Federal Open Market Committee (September 19-20, 2023) states: In determining the extent of additional policy firming that may be appropriate to return inflation to 2 percent over time, members concurred that they would take into account the cumulative tightening of (`chk-b4f73f0cfcea8d65133d`)
