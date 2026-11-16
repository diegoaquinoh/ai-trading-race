import type { Citation, ResearchNote } from '../api/types';
import { humanize } from '../lib/format';
import { Tag } from './Badges';
import { CitationChip, UnresolvedCitation } from './CitationDrawer';
import { IdList, StringList } from './Layout';

const STATUS_TONE: Record<string, 'ok' | 'warn' | 'fail'> = {
    supported: 'ok',
    insufficient_evidence: 'warn',
    contradictory_evidence: 'fail',
};

const VALIDATION_TONE: Record<string, 'ok' | 'warn' | 'fail' | 'muted'> = {
    valid: 'ok',
    invalid: 'fail',
    review_required: 'warn',
    unvalidated: 'muted',
};

/**
 * Structured research note (spec 13.1): concise explanation, cited claims,
 * numerical findings, hypotheses, counterevidence and coverage gaps. There is no
 * chain-of-thought in the contract and none is displayed.
 */
export function ResearchNoteView({ note, onOpenCitation }: { note: ResearchNote; onOpenCitation: (c: Citation) => void }) {
    const citations = note.citations ?? [];
    const byId = new Map(citations.map((c, i) => [c.citationId, { citation: c, index: i }]));
    const chips = (ids: string[] | undefined) =>
        (ids ?? []).map(id => {
            const hit = byId.get(id);
            return hit
                ? <CitationChip key={id} citation={hit.citation} index={hit.index} onOpen={onOpenCitation} />
                : <UnresolvedCitation key={id} id={id} />;
        });

    return (
        <div className="fi-note">
            <div className="fi-note-status">
                <span>Research status:</span>
                <Tag tone={STATUS_TONE[note.status] ?? 'muted'}>{humanize(note.status)}</Tag>
            </div>

            {note.explanation && (
                <div className="fi-note-block">
                    <h4>Concise rationale</h4>
                    <p className="fi-note-explanation">{note.explanation}</p>
                </div>
            )}

            <div className="fi-note-block">
                <h4>Documentary claims ({(note.claims ?? []).length})</h4>
                {(note.claims ?? []).length === 0 ? <p className="fi-muted-note">No documentary claims.</p> : (
                    <ul className="fi-claims">
                        {(note.claims ?? []).map(claim => (
                            <li key={claim.claimId}>
                                <div className="fi-claim-head">
                                    <code className="fi-code">{claim.claimId}</code>
                                    {claim.material !== false && <Tag tone="neutral">material</Tag>}
                                    <Tag tone={VALIDATION_TONE[claim.validationStatus ?? 'unvalidated'] ?? 'muted'}>
                                        {humanize(claim.validationStatus ?? 'unvalidated')}
                                    </Tag>
                                </div>
                                <p>{claim.text}</p>
                                <div className="fi-chips">
                                    {claim.citationIds.length === 0
                                        ? <Tag tone="fail">no citation</Tag>
                                        : chips(claim.citationIds)}
                                </div>
                                {(claim.validationNotes ?? []).length > 0 && <StringList items={claim.validationNotes} />}
                            </li>
                        ))}
                    </ul>
                )}
            </div>

            <div className="fi-note-block">
                <h4>Numerical findings ({(note.numericalFindings ?? []).length})</h4>
                {(note.numericalFindings ?? []).length === 0 ? <p className="fi-muted-note">No numerical findings.</p> : (
                    <ul className="fi-claims">
                        {(note.numericalFindings ?? []).map(f => (
                            <li key={f.findingId}>
                                <div className="fi-claim-head">
                                    <code className="fi-code">{f.findingId}</code>
                                    <Tag tone={VALIDATION_TONE[f.validationStatus ?? 'unvalidated'] ?? 'muted'}>{humanize(f.validationStatus ?? 'unvalidated')}</Tag>
                                </div>
                                <p>{f.text}</p>
                                <div className="fi-small">Calculation ids: <IdList ids={f.calculationIds} empty="none (unsupported)" /></div>
                                {(f.inputSnapshotIds ?? []).length > 0 && (
                                    <div className="fi-small">Input snapshots: <IdList ids={f.inputSnapshotIds} /></div>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
            </div>

            <div className="fi-note-block">
                <h4>Hypotheses and scenarios ({(note.hypotheses ?? []).length})</h4>
                {(note.hypotheses ?? []).length === 0 ? <p className="fi-muted-note">No hypotheses.</p> : (
                    <ul className="fi-claims">
                        {(note.hypotheses ?? []).map(h => (
                            <li key={h.hypothesisId}>
                                <div className="fi-claim-head">
                                    <code className="fi-code">{h.hypothesisId}</code>
                                    <Tag tone="muted">hypothesis, not a forecast fact</Tag>
                                </div>
                                <p>{h.text}</p>
                                {h.assumptions.length > 0 && <div className="fi-small">Assumptions:</div>}
                                <StringList items={h.assumptions} empty="No assumptions declared." />
                                {(h.scenarioIds ?? []).length > 0 && <div className="fi-small">Scenarios: <IdList ids={h.scenarioIds} /></div>}
                                {(h.supportingCitationIds ?? []).length > 0 && <div className="fi-chips">{chips(h.supportingCitationIds)}</div>}
                            </li>
                        ))}
                    </ul>
                )}
            </div>

            <div className="fi-note-grid">
                <div className="fi-note-block">
                    <h4>Counterevidence</h4>
                    <StringList items={note.counterevidence} empty="None reported." />
                </div>
                <div className="fi-note-block">
                    <h4>Coverage gaps</h4>
                    <StringList items={note.coverageGaps} empty="None reported." />
                </div>
            </div>

            <div className="fi-small">Retrieval runs: <IdList ids={note.retrievalRunIds} /></div>
        </div>
    );
}
