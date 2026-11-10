import { useState } from 'react';
import type { FormEvent } from 'react';
import { useResearchNote } from '../api/hooks';
import type { Citation, ResearchNote, ResponseMode } from '../api/types';
import { CitationDrawer } from '../components/CitationDrawer';
import { JsonDetails, KeyValueGrid, Notice, PageHeader, Panel } from '../components/Layout';
import { ResearchNoteView } from '../components/ResearchNoteView';
import { InlineError } from '../components/States';
import { asObject, pick, pickStr } from '../lib/read';

/** The engine may return the note bare, wrapped, or as an accepted job. */
function extractNote(body: unknown): { note: ResearchNote | null; jobId?: string; status?: string } {
    const candidate = pick(body, 'researchNote', 'note', 'result.researchNote', 'result') ?? body;
    const obj = asObject(candidate);
    if (obj && typeof obj.status === 'string' && (Array.isArray(obj.claims) || typeof obj.explanation === 'string' || Array.isArray(obj.citations))) {
        return { note: obj as unknown as ResearchNote };
    }
    return { note: null, jobId: pickStr(body, 'jobId', 'requestId'), status: pickStr(body, 'state', 'status', 'jobState') };
}

export function ResearchPage() {
    const mutation = useResearchNote();
    const [question, setQuestion] = useState('');
    const [cutoffDate, setCutoffDate] = useState('');
    const [cutoffTime, setCutoffTime] = useState('23:00');
    const [evidenceSnapshotId, setEvidenceSnapshotId] = useState('');
    const [indexBuildId, setIndexBuildId] = useState('');
    const [retrievalMode, setRetrievalMode] = useState('hybrid_rag_v1');
    const [responseMode, setResponseMode] = useState<ResponseMode>('recorded_replay');
    const [citation, setCitation] = useState<Citation | null>(null);

    const asOf = cutoffDate ? `${cutoffDate}T${cutoffTime || '00:00'}:00Z` : undefined;
    const result = mutation.data ? extractNote(mutation.data.note) : null;

    const submit = (e: FormEvent) => {
        e.preventDefault();
        if (!question.trim()) return;
        mutation.mutate({
            question: question.trim(),
            asOf,
            evidenceSnapshotId: evidenceSnapshotId.trim() || undefined,
            indexBuildId: indexBuildId.trim() || undefined,
            retrievalMode,
            responseMode,
        });
    };

    return (
        <div className="fi-page">
            <PageHeader
                icon="fa-question-circle"
                title="Research question"
                breadcrumbs={[{ to: '/fi', label: 'Research lab' }]}
                subtitle="Ask a question scoped to an information cutoff and receive a cited research note."
            />
            <Notice tone="warn" icon="fa-hand-paper">
                <strong>Informational only.</strong> Research notes have no order authority: they cannot submit, size or approve
                orders, and they do not change any portfolio.
            </Notice>

            <Panel title="Question" icon="fa-edit">
                <form className="fi-research-form" onSubmit={submit}>
                    <label className="fi-research-question">Question
                        <textarea className="fi-textarea" rows={4} maxLength={4000} value={question}
                            onChange={e => setQuestion(e.target.value)}
                            placeholder="e.g. What did the most recent FOMC statement say about the policy rate path?" />
                        <span className="fi-small">{question.length}/4000</span>
                    </label>
                    <div className="fi-filters">
                        <label>Information cutoff date (UTC)
                            <input type="date" value={cutoffDate} onChange={e => setCutoffDate(e.target.value)} />
                        </label>
                        <label>Cutoff time (UTC)
                            <input type="time" value={cutoffTime} onChange={e => setCutoffTime(e.target.value)} />
                        </label>
                        <label>Retrieval
                            <select value={retrievalMode} onChange={e => setRetrievalMode(e.target.value)}>
                                <option value="hybrid_rag_v1">Hybrid RAG (lexical + vector)</option>
                                <option value="graph_rag_v1">Graph RAG (hybrid + graph)</option>
                            </select>
                        </label>
                        <label>Responses
                            <select value={responseMode} onChange={e => setResponseMode(e.target.value as ResponseMode)}>
                                <option value="recorded_replay">Recorded replay</option>
                                <option value="fresh_inference">Fresh inference</option>
                            </select>
                        </label>
                        <label>Evidence snapshot (optional)
                            <input type="text" value={evidenceSnapshotId} onChange={e => setEvidenceSnapshotId(e.target.value)} placeholder="latest READY" />
                        </label>
                        <label>Index build (optional)
                            <input type="text" value={indexBuildId} onChange={e => setIndexBuildId(e.target.value)} placeholder="latest READY" />
                        </label>
                    </div>
                    <p className="fi-small">
                        Cutoff sent: <span className="mono">{asOf ?? 'none (engine default)'}</span>. Only passages available at or before the
                        cutoff are eligible.
                    </p>
                    <button className="fi-button" type="submit" disabled={!question.trim() || mutation.isPending}>
                        <i className={`fas ${mutation.isPending ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`}></i> Ask
                    </button>
                    <InlineError error={mutation.error} />
                </form>
            </Panel>

            {mutation.data && (
                <Panel title="Research note" icon="fa-file-alt">
                    <Notice icon="fa-info-circle">
                        Order authority: <strong>{mutation.data.orderAuthority ? 'yes' : 'none'}</strong>. This note is an informational
                        research output.
                    </Notice>
                    {result?.note ? (
                        <ResearchNoteView note={result.note} onOpenCitation={setCitation} />
                    ) : (
                        <KeyValueGrid
                            columns={2}
                            items={[
                                { label: 'Status', value: result?.status ?? 'accepted' },
                                { label: 'Job / request id', value: <span className="mono">{result?.jobId ?? 'not returned'}</span> },
                            ]}
                        />
                    )}
                    <JsonDetails value={mutation.data.note} summary="Raw response" />
                </Panel>
            )}
            <CitationDrawer citation={citation} onClose={() => setCitation(null)} />
        </div>
    );
}
