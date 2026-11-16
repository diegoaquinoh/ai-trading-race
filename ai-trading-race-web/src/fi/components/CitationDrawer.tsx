import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useEvidenceBundle, useEvidenceChunk } from '../api/hooks';
import type { Citation, DeliveredChunk, EvidenceChunkDetail } from '../api/types';
import { LoadingSpinner } from '../../components/common';
import { describeError, isNotFound } from '../lib/errors';
import { locatePassage } from '../lib/passage';
import { ChannelBadge, Tag } from './Badges';
import { Instant } from './Instant';
import { KeyValueGrid } from './Layout';

export function CitationChip({ citation, index, onOpen }: { citation: Citation; index?: number; onOpen: (c: Citation) => void }) {
    return (
        <button
            type="button"
            className="fi-citation-chip"
            onClick={() => onOpen(citation)}
            title={`Open cited passage: chunk ${citation.chunkId}, document version ${citation.documentVersionId}`}
        >
            <i className="fas fa-quote-right"></i> {index !== undefined ? `[${index + 1}]` : citation.citationId}
        </button>
    );
}

/** A missing citation id is shown explicitly, never silently dropped. */
export function UnresolvedCitation({ id }: { id: string }) {
    return (
        <span className="fi-citation-chip fi-citation-unresolved" title="Citation id not present in the delivered citations list">
            <i className="fas fa-unlink"></i> {id}
        </span>
    );
}

interface DrawerSource {
    title?: string;
    sourceUrl?: string;
    publishedAt?: string;
    availableAt?: string;
    availabilityPolicy?: string;
    headingPath?: string[];
    startOffset?: number;
    endOffset?: number;
    text?: string;
    versionId?: string;
    fidelityFlags?: string[];
    synthetic?: boolean;
    channels?: string[];
    origin: 'chunk_endpoint' | 'bundle';
}

function fromChunk(chunk: EvidenceChunkDetail): DrawerSource {
    return {
        title: chunk.documentTitle ?? chunk.title,
        sourceUrl: chunk.sourceUrl,
        publishedAt: chunk.publishedAt,
        availableAt: chunk.availableAt,
        availabilityPolicy: chunk.availabilityPolicy,
        headingPath: chunk.headingPath,
        startOffset: chunk.startOffset,
        endOffset: chunk.endOffset,
        text: chunk.text ?? chunk.normalizedText,
        versionId: chunk.versionId,
        fidelityFlags: chunk.fidelityFlags,
        synthetic: chunk.synthetic,
        origin: 'chunk_endpoint',
    };
}

function fromDelivered(chunk: DeliveredChunk): DrawerSource {
    return {
        title: chunk.title,
        sourceUrl: chunk.sourceUrl,
        publishedAt: chunk.publishedAt,
        availableAt: chunk.availableAt,
        availabilityPolicy: chunk.availabilityPolicy,
        headingPath: chunk.headingPath,
        startOffset: chunk.startOffset,
        endOffset: chunk.endOffset,
        text: chunk.text,
        versionId: chunk.versionId,
        fidelityFlags: chunk.fidelityFlags,
        synthetic: chunk.synthetic,
        channels: chunk.provenance?.channels,
        origin: 'bundle',
    };
}

function safeHttpUrl(url: string | undefined): string | undefined {
    if (!url) return undefined;
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : undefined;
    } catch {
        return undefined;
    }
}

export function CitationDrawer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
    const chunkQuery = useEvidenceChunk(citation?.chunkId);
    const fallback = !!citation && chunkQuery.isError && isNotFound(chunkQuery.error);
    const bundleQuery = useEvidenceBundle(fallback ? citation?.bundleId : undefined, 1, 200);

    useEffect(() => {
        if (!citation) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [citation, onClose]);

    if (!citation) return null;

    let source: DrawerSource | null = null;
    if (chunkQuery.data) source = fromChunk(chunkQuery.data);
    else if (bundleQuery.data) {
        const hit = bundleQuery.data.chunks.find(c => c.chunkId === citation.chunkId);
        if (hit) source = fromDelivered(hit);
    }
    const loading = chunkQuery.isLoading || bundleQuery.isLoading;
    const failed = !loading && !source;
    const failure = bundleQuery.error ?? chunkQuery.error;

    const passage = source?.text !== undefined ? locatePassage(source.text, citation) : null;
    const versionMismatch = source?.versionId && citation.documentVersionId && source.versionId !== citation.documentVersionId;
    const url = safeHttpUrl(source?.sourceUrl);

    return (
        <div className="fi-drawer-backdrop" onClick={onClose}>
            <aside className="fi-drawer" role="dialog" aria-label="Cited source passage" onClick={e => e.stopPropagation()}>
                <div className="fi-drawer-header">
                    <h3><i className="fas fa-quote-right"></i> Cited passage</h3>
                    <button onClick={onClose} aria-label="Close"><i className="fas fa-times"></i></button>
                </div>

                {loading && <LoadingSpinner size="sm" message="Loading source version…" />}
                {failed && (
                    <p className="fi-inline-error" role="alert">
                        <i className="fas fa-exclamation-triangle"></i> The cited chunk could not be resolved
                        {failure ? `: ${describeError(failure)}` : ' in its delivered bundle.'}
                    </p>
                )}

                {source && (
                    <>
                        <h4 className="fi-drawer-title">{source.title ?? 'Untitled document'}</h4>
                        <div className="fi-drawer-tags">
                            {source.synthetic && <Tag tone="warn">synthetic fixture</Tag>}
                            {(source.channels ?? []).map(ch => <ChannelBadge key={ch} channel={ch} />)}
                            {(source.fidelityFlags ?? []).map(f => <Tag key={f} tone="muted" title="Parser fidelity flag">{f}</Tag>)}
                            <Tag tone="muted" title="Where this text was loaded from">
                                {source.origin === 'chunk_endpoint' ? 'stored normalized chunk' : 'delivered bundle copy'}
                            </Tag>
                        </div>
                        {versionMismatch && (
                            <p className="fi-inline-error">
                                <i className="fas fa-exclamation-triangle"></i> Loaded version {source.versionId} differs from the cited
                                version {citation.documentVersionId}.
                            </p>
                        )}
                        <KeyValueGrid
                            columns={2}
                            items={[
                                { label: 'Source URL', value: url ? <a href={url} target="_blank" rel="noopener noreferrer">{url} <i className="fas fa-external-link-alt"></i></a> : source.sourceUrl },
                                { label: 'Document version', value: <code className="fi-code">{citation.documentVersionId}</code> },
                                { label: 'Published (source)', value: <Instant value={source.publishedAt} context="market" /> },
                                { label: 'Available (policy)', value: <Instant value={source.availableAt} context="market" />, hint: source.availabilityPolicy },
                                { label: 'Chunk', value: <code className="fi-code">{citation.chunkId}</code> },
                                {
                                    label: 'Chunk offsets in document',
                                    value: source.startOffset !== undefined ? `${source.startOffset}–${source.endOffset}` : undefined,
                                },
                                {
                                    label: 'Cited offsets in chunk',
                                    value: citation.startOffset !== undefined && citation.startOffset !== null
                                        ? `${citation.startOffset}–${citation.endOffset}` : 'not declared',
                                },
                                { label: 'Bundle', value: <Link to={`/fi/evidence/${encodeURIComponent(citation.bundleId)}`}>{citation.bundleId}</Link> },
                            ]}
                        />
                        {source.headingPath && source.headingPath.length > 0 && (
                            <p className="fi-heading-path"><i className="fas fa-sitemap"></i> {source.headingPath.join(' › ')}</p>
                        )}
                        {passage && (
                            <>
                                <p className={`fi-passage-status fi-passage-${passage.method}`}>
                                    {passage.method === 'offsets' && <><i className="fas fa-check"></i> Quote matches the stored text at the declared offsets.</>}
                                    {passage.method === 'offsets_unverified' && <><i className="fas fa-info-circle"></i> Highlighted from declared offsets (no quote to compare).</>}
                                    {passage.method === 'quote_search' && <><i className="fas fa-exclamation-triangle"></i> Declared offsets did not match; quote located by exact search.</>}
                                    {passage.method === 'not_found' && <><i className="fas fa-times"></i> The quoted text was not found in the stored normalized text.</>}
                                    {passage.method === 'none' && <><i className="fas fa-info-circle"></i> No quote or offsets declared; full chunk shown.</>}
                                </p>
                                <blockquote className="fi-passage">
                                    {passage.before}
                                    {passage.match && <mark>{passage.match}</mark>}
                                    {passage.after}
                                </blockquote>
                                {passage.method === 'not_found' && citation.quote && (
                                    <p className="fi-muted-note">Cited quote: “{citation.quote}”</p>
                                )}
                            </>
                        )}
                    </>
                )}
            </aside>
        </div>
    );
}
