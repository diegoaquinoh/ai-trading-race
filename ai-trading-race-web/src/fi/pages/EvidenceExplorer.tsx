import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useEvidenceBundle, useEvidenceGraph, useInstrumentValuation } from '../api/hooks';
import type {
    Citation,
    DeliveredChunk,
    EvidenceBundle,
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    StructuredFact,
    SupportSpan,
} from '../api/types';
import { ChannelBadge, PassFail, SyntheticBadge, Tag, ValueKindTag } from '../components/Badges';
import { CitationDrawer } from '../components/CitationDrawer';
import { EvidenceGraphView } from '../components/EvidenceGraphView';
import { Instant, TimeLegend } from '../components/Instant';
import { IdList, KeyValueGrid, Notice, PageHeader, Panel } from '../components/Layout';
import { Pagination } from '../components/Pagination';
import { QueryState } from '../components/States';
import { isNotFound } from '../lib/errors';
import { DASH, fmtNumber, fmtPct, fmtPrice, humanize } from '../lib/format';
import { isSyntheticTerms, readInstrumentValuation } from '../lib/instrument';

export function EvidenceExplorer() {
    const { bundleId } = useParams();
    const navigate = useNavigate();
    const [input, setInput] = useState('');

    if (!bundleId) {
        return (
            <div className="fi-page">
                <PageHeader icon="fa-search" title="Evidence explorer" breadcrumbs={[{ to: '/fi', label: 'Research lab' }]}
                    subtitle="Inspect the exact passages and graph provenance delivered to a strategy. Bundles are linked from each decision." />
                <Panel title="Open a bundle" icon="fa-folder-open">
                    <form className="fi-filters" onSubmit={e => { e.preventDefault(); if (input.trim()) navigate(`/fi/evidence/${encodeURIComponent(input.trim())}`); }}>
                        <label>Bundle id
                            <input type="text" value={input} onChange={e => setInput(e.target.value)} placeholder="bundle-…" />
                        </label>
                        <button className="fi-button" type="submit" disabled={!input.trim()}><i className="fas fa-arrow-right"></i> Open</button>
                    </form>
                </Panel>
            </div>
        );
    }

    return <BundlePage bundleId={bundleId} />;
}

function BundlePage({ bundleId }: { bundleId: string }) {
    const [page, setPage] = useState(1);
    const query = useEvidenceBundle(bundleId, page, 25);
    const [citation, setCitation] = useState<Citation | null>(null);

    return (
        <div className="fi-page">
            <PageHeader icon="fa-search" title={<span className="mono">{bundleId}</span>}
                breadcrumbs={[{ to: '/fi', label: 'Research lab' }, { to: '/fi/evidence', label: 'Evidence' }]}
                subtitle="Delivered passages and graph provenance, permission-scoped." />
            <TimeLegend />
            <QueryState query={query} label="evidence bundle" notFoundMessage={`Evidence bundle '${bundleId}' was not found.`}>
                {bundle => (
                    <>
                        <BundleSummary bundle={bundle} />
                        <Panel title={`Delivered passages (${bundle.totalCount ?? bundle.chunkCount ?? bundle.chunks.length})`} icon="fa-paragraph">
                            {bundle.empty || bundle.chunks.length === 0
                                ? <Notice tone="warn">The retrieval returned no eligible passages (empty bundle). Dependent strategies must abstain or fail explicitly.</Notice>
                                : bundle.chunks.map(chunk => (
                                    <ChunkCard key={chunk.chunkId} chunk={chunk} onOpen={() => setCitation(chunkCitation(bundle.bundleId ?? bundleId, chunk))} />
                                ))}
                            {bundle.totalCount !== undefined && (
                                <Pagination page={bundle.page ?? page} pageSize={bundle.pageSize ?? 25} totalCount={bundle.totalCount} onPage={setPage} label="passages" />
                            )}
                        </Panel>
                        <GraphSection bundleId={bundleId} bundle={bundle} onOpenCitation={setCitation} />
                    </>
                )}
            </QueryState>
            <CitationDrawer citation={citation} onClose={() => setCitation(null)} />
        </div>
    );
}

function chunkCitation(bundleId: string, chunk: DeliveredChunk): Citation {
    return { citationId: chunk.chunkId, bundleId, chunkId: chunk.chunkId, documentVersionId: chunk.versionId };
}

function BundleSummary({ bundle }: { bundle: EvidenceBundle }) {
    return (
        <Panel title="Bundle" icon="fa-info-circle">
            <KeyValueGrid
                columns={4}
                items={[
                    { label: 'Retrieval mode', value: <Tag tone="neutral">{bundle.mode}</Tag> },
                    { label: 'Information cutoff', value: <Instant value={bundle.decisionAsOf} context="market" /> },
                    { label: 'Index build', value: <span className="mono">{bundle.indexBuildId}</span> },
                    { label: 'Evidence snapshot', value: <span className="mono">{bundle.snapshotId}</span> },
                    { label: 'Retrieval run', value: <span className="mono">{bundle.retrievalRunId}</span> },
                    { label: 'Chunks / tokens', value: `${bundle.chunkCount ?? bundle.chunks.length} / ${bundle.totalTokens ?? DASH}` },
                    { label: 'Truncated by budget', value: <IdList ids={bundle.truncatedByBudget} /> },
                    { label: 'Structured facts', value: (bundle.structuredFacts ?? []).length },
                ]}
            />
        </Panel>
    );
}

function ChunkCard({ chunk, onOpen }: { chunk: DeliveredChunk; onOpen: () => void }) {
    const prov = chunk.provenance;
    const checks = [...(prov?.availabilityChecks ?? []), ...(prov?.graph?.availabilityChecks ?? [])];
    const allPassed = checks.length === 0 ? null : checks.every(c => c.passed);
    return (
        <article className="fi-chunk">
            <div className="fi-chunk-head">
                <span className="fi-chunk-rank mono">#{prov?.finalRank ?? chunk.ordinal}</span>
                <div className="fi-chunk-title">
                    <strong>{chunk.title}</strong>
                    {chunk.headingPath.length > 0 && <div className="fi-small">{chunk.headingPath.join(' › ')}</div>}
                </div>
                <div className="fi-chunk-badges">
                    {(prov?.channels ?? []).map(c => <ChannelBadge key={c} channel={c} />)}
                    {prov?.graph?.addedByGraph && <Tag tone="neutral" title="Not among the lexical/vector candidates">added by graph</Tag>}
                    {chunk.synthetic && <SyntheticBadge />}
                    {(chunk.fidelityFlags ?? []).map(f => <Tag key={f} tone="muted">{f}</Tag>)}
                </div>
            </div>
            <p className="fi-chunk-text">{chunk.text.length > 420 ? `${chunk.text.slice(0, 420)}…` : chunk.text}</p>
            <div className="fi-chunk-meta">
                <span>published <Instant value={chunk.publishedAt} context="market" inline /></span>
                <span>available <Instant value={chunk.availableAt} context="market" inline /></span>
                <span className="mono">offsets {chunk.startOffset}–{chunk.endOffset}</span>
                <span className="mono">{chunk.versionId}</span>
                <span>availability checks <PassFail passed={allPassed} label={allPassed === null ? 'not listed' : allPassed ? 'passed' : 'FAILED'} /></span>
                {prov?.fusedScore && <span className="mono" title="Fused rank score (review aid)">score {prov.fusedScore}</span>}
            </div>
            {prov?.graph && (
                <div className="fi-small">
                    Graph path from seed <code className="fi-code">{prov.graph.seedId}</code> via {prov.graph.pathLength} assertion(s): <IdList ids={prov.graph.pathAssertionIds} />
                </div>
            )}
            <button className="fi-link-button" onClick={onOpen}><i className="fas fa-book-open"></i> Open exact source version</button>
        </article>
    );
}

/** Builds a bounded graph from the bundle's structured facts when the graph endpoint is unavailable. */
function graphFromFacts(facts: StructuredFact[]): EvidenceGraph {
    const nodes = new Map<string, EvidenceGraphNode>();
    const edges: EvidenceGraphEdge[] = [];
    for (const f of facts) {
        if (!nodes.has(f.subjectId)) nodes.set(f.subjectId, { nodeId: f.subjectId, nodeType: 'Subject', label: f.subjectLabel });
        if (!nodes.has(f.objectId)) nodes.set(f.objectId, { nodeId: f.objectId, nodeType: 'Object', label: f.objectLabel });
        edges.push({ assertionId: f.assertionId, subjectId: f.subjectId, objectId: f.objectId, relation: f.relation, support: f.support, availableAt: f.availableAt });
    }
    return { nodes: [...nodes.values()], edges };
}

function GraphSection({ bundleId, bundle, onOpenCitation }: { bundleId: string; bundle: EvidenceBundle; onOpenCitation: (c: Citation) => void }) {
    const graphQuery = useEvidenceGraph(bundleId);
    const [edge, setEdge] = useState<EvidenceGraphEdge | null>(null);
    const [node, setNode] = useState<EvidenceGraphNode | null>(null);
    const facts = bundle.structuredFacts ?? [];
    const fallback = graphQuery.isError && isNotFound(graphQuery.error) && facts.length > 0 ? graphFromFacts(facts) : null;
    const graph = graphQuery.data ?? fallback;
    const labelOf = (id: string) => graph?.nodes.find(n => n.nodeId === id)?.label ?? id;

    return (
        <Panel title="Graph provenance" icon="fa-project-diagram">
            {fallback && (
                <p className="fi-muted-note"><i className="fas fa-info-circle"></i> Graph endpoint unavailable; showing the structured facts delivered in this bundle.</p>
            )}
            {graph ? (
                <div className="fi-graph-layout">
                    <EvidenceGraphView
                        graph={graph}
                        selectedEdgeId={edge?.assertionId}
                        selectedNodeId={node?.nodeId}
                        onSelectEdge={e => { setEdge(e); setNode(null); }}
                        onSelectNode={n => { setNode(n); setEdge(null); }}
                    />
                    <div className="fi-graph-detail">
                        {!edge && !node && <p className="fi-muted-note">Select an edge to see its supporting assertions, or an instrument node to join its current valuation.</p>}
                        {edge && <EdgeDetail edge={edge} bundleId={bundleId} labelOf={labelOf} onOpenCitation={onOpenCitation} />}
                        {node && <NodeDetail node={node} />}
                    </div>
                </div>
            ) : (
                <QueryState query={graphQuery} label="graph" compact
                    notFoundMessage="The bounded graph view is not available for this bundle (endpoint not deployed or no graph provenance).">
                    {() => null}
                </QueryState>
            )}
        </Panel>
    );
}

function spanCitation(bundleId: string, span: SupportSpan, id: string): Citation | null {
    if (span.kind !== 'chunk_span' || !span.chunkId) return null;
    return {
        citationId: id,
        bundleId,
        chunkId: span.chunkId,
        documentVersionId: span.versionId ?? '',
        quote: span.quote,
        startOffset: span.startOffset,
        endOffset: span.endOffset,
    };
}

function EdgeDetail({ edge, bundleId, labelOf, onOpenCitation }: {
    edge: EvidenceGraphEdge;
    bundleId: string;
    labelOf: (id: string) => string;
    onOpenCitation: (c: Citation) => void;
}) {
    return (
        <div>
            <h3 className="fi-h3"><ValueKindTag kind="graph" /> {edge.relation}</h3>
            <p className="fi-small">{labelOf(edge.subjectId)} <i className="fas fa-long-arrow-alt-right"></i> {labelOf(edge.objectId)}</p>
            <KeyValueGrid
                columns={2}
                items={[
                    { label: 'Assertion', value: <span className="mono">{edge.assertionId}</span> },
                    { label: 'Available at', value: <Instant value={edge.availableAt} context="market" /> },
                    { label: 'Extraction method', value: edge.extractionMethod },
                    { label: 'Extraction version / run', value: edge.extractionVersion ? `${edge.extractionVersion} · ${edge.extractionRunId ?? DASH}` : undefined },
                    { label: 'Validation status', value: edge.validationStatus ? <Tag tone={edge.validationStatus === 'approved' ? 'ok' : 'warn'}>{edge.validationStatus}</Tag> : undefined },
                    { label: 'Confidence (review aid only)', value: edge.confidence },
                ]}
            />
            {(edge.inputIds ?? []).length > 0 && <div className="fi-small">Inputs inherited for availability: <IdList ids={edge.inputIds} /></div>}
            <h4>Supporting assertions</h4>
            {(edge.support ?? []).length === 0 ? <p className="fi-muted-note">No support spans returned.</p> : (
                <ul className="fi-support">
                    {(edge.support ?? []).map((s, i) => {
                        const c = spanCitation(bundleId, s, `${edge.assertionId}#${i}`);
                        return (
                            <li key={i}>
                                <Tag tone="muted">{humanize(s.kind)}</Tag>
                                {s.quote && <q>{s.quote}</q>}
                                {s.sourceRef && <span className="mono fi-small"> {s.sourceRef}</span>}
                                {s.chunkId && <span className="mono fi-small"> {s.chunkId}{s.startOffset !== null && s.startOffset !== undefined ? ` [${s.startOffset}–${s.endOffset}]` : ''}</span>}
                                {c && <button className="fi-link-button" onClick={() => onOpenCitation(c)}>open passage</button>}
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}

function NodeDetail({ node }: { node: EvidenceGraphNode }) {
    const isInstrument = node.nodeType === 'Instrument';
    return (
        <div>
            <h3 className="fi-h3"><ValueKindTag kind="graph" /> {node.label}</h3>
            <KeyValueGrid
                columns={2}
                items={[
                    { label: 'Node', value: <span className="mono">{node.nodeId}</span> },
                    { label: 'Type', value: node.nodeType },
                    { label: 'Available at', value: <Instant value={node.availableAt} context="market" /> },
                    ...Object.entries(node.properties ?? {}).map(([k, v]) => ({ label: humanize(k), value: v })),
                ]}
            />
            {isInstrument && <InstrumentJoin securityId={node.properties?.securityId ?? node.properties?.security_id ?? node.label ?? node.nodeId} />}
        </div>
    );
}

function InstrumentJoin({ securityId }: { securityId: string }) {
    const query = useInstrumentValuation(securityId);
    return (
        <div className="fi-join">
            <h4><ValueKindTag kind="calculated" /> Current valuation and risk</h4>
            <p className="fi-small">Joined from the valuation engine for <Link to={`/fi/instruments/${encodeURIComponent(securityId)}`} className="mono">{securityId}</Link>. These are calculated values, not facts stored in the graph.</p>
            <QueryState query={query} label="instrument valuation" compact notFoundMessage="Instrument valuation is not available (endpoint not deployed or unknown security).">
                {data => {
                    const v = readInstrumentValuation(data);
                    return (
                        <>
                            {(isSyntheticTerms(v.terms, securityId) || v.synthetic) && <SyntheticBadge />}
                            <KeyValueGrid
                                columns={2}
                                items={[
                                    { label: 'Curve-model clean (per 100)', value: fmtPrice(v.model.cleanPricePer100) },
                                    { label: 'Curve-model dirty (per 100)', value: fmtPrice(v.model.dirtyPricePer100) },
                                    { label: 'YTM', value: fmtPct(v.model.ytm ?? v.risk.ytm, 4) },
                                    { label: 'Effective duration', value: v.risk.effectiveDurationYears ? `${fmtNumber(v.risk.effectiveDurationYears, 3)} y` : undefined },
                                    { label: 'Parallel DV01', value: v.risk.parallelDv01 ? `${fmtNumber(v.risk.parallelDv01, 4)}${v.risk.dv01Basis ? ` (${v.risk.dv01Basis})` : ''}` : undefined },
                                    { label: 'Valuation date', value: v.valuationDate },
                                ]}
                            />
                        </>
                    );
                }}
            </QueryState>
        </div>
    );
}
