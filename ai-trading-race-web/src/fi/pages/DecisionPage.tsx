import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useDecision } from '../api/hooks';
import type {
    Citation,
    DecisionAttempt,
    DecisionDetail,
    PolicyEvaluationView,
    SpecialistTask,
    TargetWeight,
    ToolTrace,
} from '../api/types';
import { KindBadge, OutcomeBadge, PassFail, Tag } from '../components/Badges';
import { CitationDrawer } from '../components/CitationDrawer';
import { Instant, SessionDate, TimeLegend } from '../components/Instant';
import { IdList, JsonDetails, KeyValueGrid, Notice, PageHeader, Panel, StringList } from '../components/Layout';
import { OrdersTable } from '../components/OrdersTable';
import { ResearchNoteView } from '../components/ResearchNoteView';
import { QueryState } from '../components/States';
import { outcomeMeta } from '../lib/domain';
import { DASH, fmtFace, fmtInt, fmtMs, fmtPct, fmtPrice, fmtUsd, humanize, shortHash } from '../lib/format';

export function DecisionPage() {
    const { decisionId } = useParams();
    const query = useDecision(decisionId);
    return (
        <div className="fi-page">
            <QueryState query={query} label="decision" notFoundMessage={`Decision '${decisionId}' was not found.`}>
                {d => <DecisionBody detail={d} />}
            </QueryState>
        </div>
    );
}

function DecisionBody({ detail }: { detail: DecisionDetail }) {
    const d = detail.decision;
    const meta = outcomeMeta(d.outcome);
    const inputs = detail.frozenInputs;
    const [citation, setCitation] = useState<Citation | null>(null);
    const closeDrawer = () => setCitation(null);
    const unfilled = detail.orders.filter(o => o.status === 'EXPIRED' || o.status === 'REJECTED' || o.status === 'CANCELLED');

    return (
        <>
            <PageHeader
                icon="fa-gavel"
                title={<span className="mono">{d.decisionId}</span>}
                breadcrumbs={[
                    { to: '/fi', label: 'Experiments' },
                    { to: `/fi/runs/${encodeURIComponent(d.runId)}`, label: d.runId },
                ]}
                subtitle={<>{d.strategyId} · repetition {d.repetition} · cycle {d.cycleId}</>}
            >
                <KindBadge kind={d.strategyKind} />
                <OutcomeBadge outcome={d.outcome} />
            </PageHeader>
            <TimeLegend />
            <Notice icon="fa-user-secret">
                This page shows the structured, auditable record of the decision: inputs, rationale summary, cited claims, tool
                outputs, policy checks and orders. No private chain-of-thought is stored or displayed.
            </Notice>

            <Panel title="Outcome and financial consequence" icon="fa-flag" className={`fi-outcome-panel fi-outcome-panel-${meta.tone}`}>
                <div className="fi-outcome-hero">
                    <OutcomeBadge outcome={d.outcome} />
                    <span className="mono">{d.action ? `action ${d.action}` : 'no action'}</span>
                    <Tag tone={d.integrity === 'verified' ? 'ok' : d.integrity === 'synthesized' ? 'muted' : 'fail'} title="Audit integrity of the stored result">integrity: {d.integrity}</Tag>
                </div>
                <p className="fi-outcome-financial"><strong>Financial behaviour:</strong> {meta.financial}</p>
                <h3 className="fi-h3">Reasons</h3>
                <StringList items={d.reasons} empty={d.outcome.startsWith('completed') ? 'No abstention, failure or skip reasons.' : 'No reason was recorded (this itself is an audit gap).'} />
                {detail.usage?.budgetExhausted && <p className="fi-inline-error"><i className="fas fa-hourglass-end"></i> Budget exhausted: {detail.usage.budgetExhausted}</p>}
                {detail.attempts.some(a => a.error) && (
                    <>
                        <h3 className="fi-h3">Attempt errors</h3>
                        <ul className="fi-reasons">
                            {detail.attempts.filter(a => a.error).map(a => <li key={a.attemptId}>#{a.attemptNumber} {a.agentRole} ({a.status}): {a.error}</li>)}
                        </ul>
                    </>
                )}
                {unfilled.length > 0 && (
                    <>
                        <h3 className="fi-h3">Orders that did not fill</h3>
                        <ul className="fi-reasons">
                            {unfilled.map(o => <li key={o.orderId}>{o.side} {o.securityId} {fmtFace(o.face)}: {o.status}{o.statusReason ? ` — ${o.statusReason}` : ''} (reserved cash released)</li>)}
                        </ul>
                    </>
                )}
                <div className="fi-small">Completed (operational): <Instant value={d.completedAt} inline /></div>
            </Panel>

            <Panel title="Frozen inputs and information cutoff" icon="fa-snowflake">
                <KeyValueGrid
                    columns={3}
                    items={[
                        { label: 'Information cutoff (decision as of)', value: <Instant value={detail.decisionAsOf} context="market" /> },
                        { label: 'Market session', value: <SessionDate value={detail.marketSessionDate} /> },
                        { label: 'Cycle', value: <span className="mono">{d.cycleId}{detail.cycleSequence != null ? ` (#${detail.cycleSequence})` : ''}</span> },
                        {
                            label: 'Portfolio snapshot',
                            value: inputs?.portfolioSnapshotId
                                ? <span className="mono" title={inputs.portfolioSnapshotHash ?? undefined}>{inputs.portfolioSnapshotId} · {shortHash(inputs.portfolioSnapshotHash)}</span>
                                : <span className="fi-muted" title="Synthesized outcomes (skips, dependency failures) were never sent a portfolio snapshot">none sent</span>,
                        },
                        { label: 'Market snapshot', value: inputs?.marketSnapshotId ? <span className="mono">{inputs.marketSnapshotId} · {shortHash(inputs.marketSnapshotHash)}</span> : undefined },
                        { label: 'Curve snapshot', value: inputs?.curveSnapshotId ? <Link to={`/fi/curves/${encodeURIComponent(inputs.curveSnapshotId)}`} className="mono">{inputs.curveSnapshotId}</Link> : undefined },
                        { label: 'Portfolio', value: detail.portfolioId ? <Link to={`/fi/portfolios/${encodeURIComponent(detail.portfolioId)}`} className="mono">{detail.portfolioId}</Link> : undefined },
                        { label: 'Request hash', value: <span className="mono">{shortHash(detail.requestHash)}</span> },
                        { label: 'Result hash', value: <span className="mono">{shortHash(detail.resultHash)}</span> },
                        { label: 'Engine', value: detail.engineVersion ?? detail.versions?.engineVersion },
                        { label: 'Evidence snapshot', value: <span className="mono">{inputs?.evidenceSnapshotId ?? detail.versions?.evidenceSnapshotId ?? DASH}</span> },
                        { label: 'Index build', value: <span className="mono">{inputs?.indexBuildId ?? detail.versions?.indexBuildId ?? DASH}</span> },
                        { label: 'Universe / strategy config', value: <span className="mono">{inputs?.instrumentUniverseVersion ?? DASH} / {inputs?.strategyConfigId ?? DASH}</span> },
                        { label: 'Risk policy / availability', value: <span className="mono">{inputs?.riskPolicyId ?? DASH} / {inputs?.availabilityPolicy ?? DASH}</span> },
                        { label: 'Retrieval mode', value: detail.versions?.retrievalMode },
                        { label: 'Provider / model', value: detail.versions?.model ? `${detail.versions.provider ?? DASH} / ${detail.versions.model}` : 'none (deterministic)' },
                        { label: 'Prompt / tool schema', value: `${detail.versions?.promptVersion ?? DASH} / ${detail.versions?.toolSchemaVersion ?? DASH}` },
                        { label: 'Strategy config hash', value: <span className="mono">{shortHash(detail.versions?.strategyConfigHash)}</span> },
                    ]}
                />
                <h3 className="fi-h3">Evidence bundles delivered</h3>
                {detail.evidenceBundleIds.length === 0 ? <p className="fi-muted-note">No evidence bundle (market-only or deterministic strategy).</p> : (
                    <div className="fi-chips">
                        {detail.evidenceBundleIds.map(id => (
                            <Link key={id} to={`/fi/evidence/${encodeURIComponent(id)}`} className="fi-citation-chip"><i className="fas fa-folder-open"></i> {id}</Link>
                        ))}
                    </div>
                )}
                {detail.inputHashes && Object.keys(detail.inputHashes).length > 0 && (
                    <>
                        <h3 className="fi-h3">Input hashes</h3>
                        <table className="fi-table fi-table-dense">
                            <tbody>
                                {Object.entries(detail.inputHashes).map(([k, v]) => (
                                    <tr key={k}><td className="mono">{k}</td><td className="mono fi-break">{String(v)}</td></tr>
                                ))}
                            </tbody>
                        </table>
                    </>
                )}
            </Panel>

            <Panel title="Proposal" icon="fa-bullseye">
                {!detail.proposal ? <p className="fi-muted-note">No proposal ({meta.label.toLowerCase()}).</p> : (
                    <>
                        <KeyValueGrid
                            columns={3}
                            items={[
                                { label: 'Declared action', value: <span className="mono">{detail.proposal.action}</span> },
                                { label: 'Supporting claims', value: <IdList ids={detail.proposal.supportingClaimIds} /> },
                                { label: 'Supporting calculations', value: <IdList ids={detail.proposal.supportingCalculationIds} /> },
                            ]}
                        />
                        <h3 className="fi-h3">Original target allocation</h3>
                        <WeightsTable weights={detail.proposal.targetWeights ?? []} />
                    </>
                )}
            </Panel>

            <Panel title="Deterministic sizing and policy checks" icon="fa-clipboard-check">
                {detail.policyEvaluations.length === 0
                    ? <p className="fi-muted-note">No policy evaluation (no proposal reached the policy gate).</p>
                    : detail.policyEvaluations.map((p, i) => <PolicyEvaluationBlock key={`${p.source}-${i}`} p={p} />)}
            </Panel>

            <Panel title="Authorized orders and later fills" icon="fa-exchange-alt">
                {detail.orders.length === 0 ? <p className="fi-muted-note">No orders were authorized by this decision.</p> : <OrdersTable orders={detail.orders} />}
                {detail.orders.length > 0 && (
                    <p className="fi-small">
                        {detail.orders.length} order(s), {(detail.fillIds ?? []).length} fill(s)
                        {(detail.fillIds ?? []).length > 0 && <> · <span className="mono">{(detail.fillIds ?? []).join(', ')}</span></>}
                        {detail.portfolioId && (
                            <> · <Link to={`/fi/portfolios/${encodeURIComponent(detail.portfolioId)}`}>portfolio orders and journal</Link></>
                        )}
                    </p>
                )}
            </Panel>

            <Panel title="Research note" icon="fa-file-alt">
                {detail.researchNote
                    ? <ResearchNoteView note={detail.researchNote} onOpenCitation={setCitation} />
                    : <p className="fi-muted-note">No research note (deterministic or market-only strategy, or failed before synthesis).</p>}
            </Panel>

            <Panel title="Validation results" icon="fa-check-double">
                {(detail.validation ?? []).length === 0 ? <p className="fi-muted-note">No validation steps recorded.</p> : (
                    <table className="fi-table fi-table-dense">
                        <thead><tr><th>Step</th><th>Result</th><th>Severity</th><th>Details</th></tr></thead>
                        <tbody>
                            {(detail.validation ?? []).map((v, i) => (
                                <tr key={`${v.step}-${i}`}>
                                    <td>{humanize(v.step)}</td>
                                    <td><PassFail passed={v.passed} /></td>
                                    <td><Tag tone={v.severity === 'blocking' ? 'fail' : v.severity === 'warning' ? 'warn' : 'muted'}>{v.severity ?? 'blocking'}</Tag></td>
                                    <td><StringList items={v.details} empty="" /></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </Panel>

            <TaskTree detail={detail} />
            <UsagePanel detail={detail} />
            <CitationDrawer citation={citation} onClose={closeDrawer} />
        </>
    );
}

function WeightsTable({ weights, compare }: { weights: TargetWeight[]; compare?: TargetWeight[] }) {
    if (weights.length === 0) return <p className="fi-muted-note">No target weights (HOLD).</p>;
    const ids = [...new Set([...weights.map(w => w.securityId), ...(compare ?? []).map(w => w.securityId)])];
    return (
        <table className="fi-table fi-table-dense">
            <thead><tr><th>Security</th><th>{compare ? 'Original' : 'Target weight'}</th>{compare && <th>Normalized</th>}</tr></thead>
            <tbody>
                {ids.map(id => (
                    <tr key={id}>
                        <td className="mono">{id === 'CASH-USD' ? 'CASH-USD (cash)' : <Link to={`/fi/instruments/${encodeURIComponent(id)}`}>{id}</Link>}</td>
                        <td className="mono">{fmtPct(weights.find(w => w.securityId === id)?.weight, 2)}</td>
                        {compare && <td className="mono">{fmtPct(compare.find(w => w.securityId === id)?.weight, 2)}</td>}
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function PolicyEvaluationBlock({ p }: { p: PolicyEvaluationView }) {
    const e = p.evaluation ?? {};
    return (
        <div className="fi-policy">
            <div className="fi-policy-head">
                <Tag tone="muted">{p.source}</Tag>
                <span className="mono">{p.policyId}</span>
                <span className="mono">{p.action}</span>
                <PassFail passed={p.passed} label={p.passed ? 'policy passed' : 'policy rejected'} />
                {p.breachMode && <Tag tone="warn">breach mode</Tag>}
                {p.bootstrapExemptionApplied && <Tag tone="muted">bootstrap turnover exemption</Tag>}
                <span>platform re-check: <PassFail passed={p.platformRecheckPassed} /></span>
            </div>
            {p.platformRecheckReasons.length > 0 && <StringList items={p.platformRecheckReasons} />}
            {(e.rejectedReasons ?? []).length > 0 && (
                <>
                    <h4>Rejection reasons</h4>
                    <StringList items={e.rejectedReasons} />
                </>
            )}
            <h4>Checks (limit vs observed)</h4>
            {(e.checks ?? []).length === 0 ? <p className="fi-muted-note">No individual checks recorded.</p> : (
                <table className="fi-table fi-table-dense">
                    <thead><tr><th>Check</th><th>Limit</th><th>Observed</th><th>Unit</th><th>Result</th><th>Reason</th></tr></thead>
                    <tbody>
                        {(e.checks ?? []).map(c => (
                            <tr key={c.checkId} className={c.passed ? '' : 'fi-row-fail'}>
                                <td>{humanize(c.checkId)}</td>
                                <td className="mono">{c.limit ?? DASH}</td>
                                <td className="mono">{c.observed ?? DASH}</td>
                                <td className="fi-small">{c.unit}</td>
                                <td><PassFail passed={c.passed} /></td>
                                <td className="fi-small">{c.reason ?? ''}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {((e.originalTargets ?? []).length > 0 || (e.normalizedTargets ?? []).length > 0) && (
                <>
                    <h4>Target normalization</h4>
                    <WeightsTable weights={e.originalTargets ?? []} compare={e.normalizedTargets ?? []} />
                    <StringList items={e.normalizationNotes} empty="" />
                </>
            )}
            <h4>Deterministic sizing</h4>
            {(e.sizedOrders ?? []).length === 0 ? <p className="fi-muted-note">No orders sized.</p> : (
                <table className="fi-table fi-table-dense">
                    <thead><tr><th>Security</th><th>Side</th><th>Face</th><th>Est. dirty per 100</th><th>Est. consideration</th></tr></thead>
                    <tbody>
                        {(e.sizedOrders ?? []).map((o, i) => (
                            <tr key={`${o.securityId}-${i}`}>
                                <td className="mono">{o.securityId}</td><td>{o.side}</td><td className="mono">{fmtFace(o.face)}</td>
                                <td className="mono">{fmtPrice(o.estimatedDirtyPricePer100)}</td><td className="mono">{fmtUsd(o.estimatedConsiderationUsd)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            <KeyValueGrid
                columns={4}
                items={[
                    { label: 'Post-trade NAV', value: fmtUsd(e.postTradeNavUsd) },
                    { label: 'Post-trade cash ratio', value: fmtPct(e.postTradeCashRatio) },
                    { label: 'Post-trade max security ratio', value: fmtPct(e.postTradeMaxSecurityRatio) },
                    { label: 'Post-trade DV01', value: fmtUsd(e.postTradeParallelDv01Usd) },
                    { label: 'Turnover ratio', value: fmtPct(e.turnoverRatio) },
                    { label: 'Order count', value: e.orderCount },
                    { label: 'Calculation ids', value: <IdList ids={e.calculationIds} /> },
                    { label: 'Command', value: <span className="mono">{p.commandId ?? DASH}</span> },
                ]}
            />
        </div>
    );
}

function AttemptsTable({ attempts }: { attempts: DecisionAttempt[] }) {
    if (attempts.length === 0) return null;
    return (
        <table className="fi-table fi-table-dense">
            <thead><tr><th>#</th><th>Purpose</th><th>Provider / model</th><th>Tokens in / out</th><th>Duration</th><th>Status</th><th>Recorded response</th></tr></thead>
            <tbody>
                {attempts.map(a => (
                    <tr key={a.attemptId} className={a.status === 'ok' ? '' : 'fi-row-fail'}>
                        <td className="mono">{a.attemptNumber}</td>
                        <td>{humanize(a.purpose)}</td>
                        <td className="fi-small">{a.provider} / {a.model}</td>
                        <td className="mono">{fmtInt(a.inputTokens)} / {fmtInt(a.outputTokens)}</td>
                        <td className="mono">{fmtMs(a.durationMs)}</td>
                        <td><Tag tone={a.status === 'ok' ? 'ok' : 'fail'}>{a.status}</Tag>{a.error && <div className="fi-small fi-fail-text">{a.error}</div>}</td>
                        <td className="mono fi-small">{a.recordedResponseId ?? DASH}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function ToolTable({ traces }: { traces: ToolTrace[] }) {
    if (traces.length === 0) return null;
    return (
        <table className="fi-table fi-table-dense">
            <thead><tr><th>Tool</th><th>Status</th><th>Output ref</th><th>Duration</th><th>Request / response summary</th></tr></thead>
            <tbody>
                {traces.map(t => (
                    <tr key={t.traceId} className={t.status === 'ok' ? '' : 'fi-row-fail'}>
                        <td className="mono">{t.toolName}</td>
                        <td><Tag tone={t.status === 'ok' ? 'ok' : 'fail'}>{t.status}</Tag>{t.error && <div className="fi-small fi-fail-text">{t.error}</div>}</td>
                        <td className="mono fi-small">{t.outputRef ?? DASH}</td>
                        <td className="mono">{fmtMs(t.durationMs)}</td>
                        <td>
                            <JsonDetails value={t.request} summary="request" />
                            <JsonDetails value={t.responseSummary} summary="response summary" />
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function TaskTree({ detail }: { detail: DecisionDetail }) {
    const tasks: SpecialistTask[] = detail.specialistTasks ?? [];
    const specialistRoles = new Set(tasks.map(t => t.role));
    const parentAttempts = detail.attempts.filter(a => !specialistRoles.has(a.agentRole));
    const parentTools = detail.toolTraces.filter(t => !specialistRoles.has(t.agentRole));
    const parentRoles = [...new Set([...parentAttempts.map(a => a.agentRole), ...parentTools.map(t => t.agentRole)])];

    return (
        <Panel title="Task tree" icon="fa-sitemap">
            {detail.attempts.length === 0 && detail.toolTraces.length === 0 && tasks.length === 0 ? (
                <p className="fi-muted-note">No model attempts or tool calls (deterministic strategy or skipped before generation).</p>
            ) : (
                <ul className="fi-tree">
                    <li>
                        <div className="fi-tree-node">
                            <i className="fas fa-user-tie"></i> <strong>{parentRoles.length ? parentRoles.join(', ') : 'parent'}</strong>
                            <span className="fi-small"> · {parentAttempts.length} model calls · {parentTools.length} tool calls</span>
                        </div>
                        <AttemptsTable attempts={parentAttempts} />
                        <ToolTable traces={parentTools} />
                        {tasks.length > 0 && (
                            <ul>
                                {tasks.map(t => (
                                    <li key={t.taskId}>
                                        <div className="fi-tree-node">
                                            <i className="fas fa-user-cog"></i> <strong>{humanize(t.role)}</strong>{' '}
                                            <Tag tone={t.status === 'completed' ? 'ok' : t.status === 'skipped' ? 'muted' : 'fail'}>{t.status}</Tag>
                                            <span className="mono fi-small"> {t.taskId}</span>
                                        </div>
                                        <p className="fi-small"><strong>Instruction:</strong> {t.instruction}</p>
                                        <div className="fi-small">Inputs: <IdList ids={t.inputSnapshotIds} /> · expected schema <span className="mono">{t.expectedOutputSchema ?? DASH}</span></div>
                                        <h4>Returned findings</h4>
                                        <StringList items={t.findings} empty="No findings returned." />
                                        <div className="fi-small">Claims: <IdList ids={t.claimIds} /></div>
                                        <div className="fi-small">
                                            Usage: {Object.entries(t.usage ?? {}).map(([k, v]) => `${humanize(k)} ${v}`).join(' · ') || DASH}
                                            {' '}| reserved: {Object.entries(t.budgetReserved ?? {}).map(([k, v]) => `${humanize(k)} ${v}`).join(' · ') || DASH}
                                        </div>
                                        <AttemptsTable attempts={detail.attempts.filter(a => a.agentRole === t.role)} />
                                        <ToolTable traces={detail.toolTraces.filter(x => x.agentRole === t.role)} />
                                    </li>
                                ))}
                            </ul>
                        )}
                    </li>
                </ul>
            )}
        </Panel>
    );
}

function UsagePanel({ detail }: { detail: DecisionDetail }) {
    const u = detail.usage;
    return (
        <Panel title="Usage" icon="fa-coins">
            {!u ? <p className="fi-muted-note">No usage recorded.</p> : (
                <KeyValueGrid
                    columns={4}
                    items={[
                        { label: 'Generation calls', value: u.generationCalls },
                        { label: 'Tool calls', value: u.toolCalls },
                        { label: 'Evidence calls', value: u.evidenceCalls },
                        { label: 'Unique evidence chunks', value: u.uniqueEvidenceChunks },
                        { label: 'Evidence tokens', value: fmtInt(u.evidenceTokens) },
                        { label: 'Input / output tokens', value: `${fmtInt(u.inputTokens)} / ${fmtInt(u.outputTokens)}` },
                        { label: 'Duration', value: fmtMs(u.durationMs) },
                        { label: 'Estimated cost', value: u.estimatedCostUsd ? `${fmtUsd(u.estimatedCostUsd, 4)} (${u.priceScheduleId ?? 'schedule n/a'})` : 'not priced' },
                        { label: 'Budget exhausted', value: u.budgetExhausted ?? 'no' },
                    ]}
                />
            )}
        </Panel>
    );
}
