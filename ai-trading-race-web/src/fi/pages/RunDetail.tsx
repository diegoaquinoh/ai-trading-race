import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useCancelRun, useCycleDecisions, useRun, useRunComparison, useRunCycles, useRunDecisions } from '../api/hooks';
import type { ClassifiedError, Cycle, DecisionSummary, RunComparison, RunDetail as RunDetailModel } from '../api/types';
import { DataModeBadge, JobStateBadge, KindBadge, OutcomeBadge, ResponseModeBadge, Tag } from '../components/Badges';
import { Instant, SessionDate, TimeLegend } from '../components/Instant';
import { JsonDetails, KeyValueGrid, Notice, PageHeader, Panel } from '../components/Layout';
import { Pagination } from '../components/Pagination';
import { InlineError, QueryState } from '../components/States';
import { EVIDENCE_OUTCOMES, OUTCOME_ORDER, isTerminalJob, outcomeMeta } from '../lib/domain';
import { DASH, fmtInt, fmtNumber, fmtPct, fmtUsd, humanize, shortHash, signClass } from '../lib/format';
import { manifestValue, strategyMetaFor } from '../lib/runMeta';

const SPEEDS = [0.5, 1, 2, 4, 8];

const INTEGRITY_HINT: Record<string, string> = {
    verified: 'Result hash recomputed and signature verified',
    synthesized: 'Recorded by the platform because no engine result exists (e.g. dependency failure or stale-data skip)',
    hash_mismatch: 'Stored result hash does not match its content',
    signature_invalid: 'Result signature could not be verified',
};
const BASE_STEP_MS = 1600;

export function RunDetail() {
    const { runId } = useParams();
    const runQuery = useRun(runId);
    const location = useLocation();

    useEffect(() => {
        if (location.hash === '#manifest' && runQuery.data) {
            document.getElementById('manifest')?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [location.hash, runQuery.data]);

    return (
        <div className="fi-page">
            <QueryState query={runQuery} label="run" notFoundMessage={`Run '${runId}' was not found.`}>
                {detail => <RunBody detail={detail} />}
            </QueryState>
        </div>
    );
}

function RunBody({ detail }: { detail: RunDetailModel }) {
    const { run } = detail;
    const cancel = useCancelRun(run.runId);
    return (
        <>
            <PageHeader
                icon="fa-play-circle"
                title={<span className="mono">{run.runId}</span>}
                breadcrumbs={[{ to: '/fi', label: 'Experiments' }]}
                subtitle={<>{run.experimentId} v{run.experimentVersion} · {run.dataModeLabel}</>}
            >
                <DataModeBadge mode={run.dataMode} label={run.dataModeLabel} />
                <ResponseModeBadge mode={run.responseMode} />
                <JobStateBadge state={run.jobState} />
                {!isTerminalJob(run.jobState) && (
                    <button className="fi-button fi-button-danger" disabled={cancel.isPending}
                        onClick={() => { if (window.confirm('Cancel uncommitted work for this run? Committed events remain authoritative.')) cancel.mutate(); }}>
                        <i className="fas fa-ban"></i> Cancel run
                    </button>
                )}
            </PageHeader>
            <InlineError error={cancel.error} />
            <TimeLegend />

            <Panel title="Run" icon="fa-info-circle">
                <KeyValueGrid
                    columns={4}
                    items={[
                        { label: 'Run type', value: run.runType === 'replay' ? 'Historical replay' : run.runType === 'forward' ? 'Forward paper cycle' : run.runType },
                        { label: 'Evaluation window', value: run.startDate ? <><SessionDate value={run.startDate} /> → <SessionDate value={run.endDate} /></> : undefined },
                        { label: 'Progress', value: `${run.completedCycles}/${run.totalCycles ?? '?'} cycles` },
                        {
                            label: 'Checkpoint',
                            value: run.checkpoint
                                ? <span title={`Resume starts after cycle #${run.checkpoint.sequence}`}>#{run.checkpoint.sequence} <span className="mono">{run.checkpoint.cycleId}</span> ({run.checkpoint.status}) · {run.checkpoint.checkpointedCycles}/{run.checkpoint.totalCycles ?? '?'} checkpointed</span>
                                : 'none yet',
                        },
                        {
                            label: 'Classified errors',
                            value: run.errors
                                ? <span title={Object.entries(run.errors.byScope).map(([k, v]) => `${k}: ${v}`).join('\n')}>{run.errors.runErrors} run · {run.errors.cycleErrors} cycle errors · {run.errors.cycleWarnings} warnings</span>
                                : undefined,
                        },
                        { label: 'Risk policy', value: <span className="mono">{run.riskPolicyId}</span> },
                        { label: 'Execution model', value: <span className="mono">{run.executionModelId}</span> },
                        { label: 'Simulated clock (market)', value: <Instant value={run.simulatedClock} context="market" /> },
                        { label: 'Created (operational)', value: <Instant value={run.createdAt} /> },
                        { label: 'Started (operational)', value: <Instant value={run.startedAt} /> },
                        { label: 'Completed (operational)', value: <Instant value={run.completedAt} /> },
                        { label: 'Engine version', value: detail.engineVersion },
                        { label: 'Manifest', value: <a href="#manifest" className="mono">{shortHash(detail.manifestHash)}</a> },
                        { label: 'Status reason', value: run.statusReason },
                    ]}
                />
                {run.errors && Object.keys(run.errors.byScope).length > 0 && (
                    <div className="fi-chips">
                        {Object.entries(run.errors.byScope).map(([scope, n]) => <Tag key={scope} tone="warn" title="Errors and warnings by scope">{humanize(scope)}: {n}</Tag>)}
                    </div>
                )}
                {(detail.runErrors ?? []).length > 0 && (
                    <>
                        <h3 className="fi-h3">Run-level errors</h3>
                        <ErrorList errors={detail.runErrors ?? []} />
                    </>
                )}
                <h3 className="fi-h3">Outcomes across all cycles</h3>
                <div className="fi-outcome-summary">
                    {OUTCOME_ORDER.map(o => (
                        <div key={o} className={`fi-outcome-tile ${detail.outcomeCounts[o] ? '' : 'zero'}`} title={outcomeMeta(o).financial}>
                            <OutcomeBadge outcome={o} />
                            <span className="mono">{detail.outcomeCounts[o] ?? 0}</span>
                        </div>
                    ))}
                </div>
            </Panel>

            <StrategiesPanel detail={detail} />
            <ReplayPanel detail={detail} />
            <ComparisonPanel runId={run.runId} />
            <DecisionsPanel detail={detail} />
            <ManifestPanel detail={detail} />
        </>
    );
}

function StrategiesPanel({ detail }: { detail: RunDetailModel }) {
    const meta = strategyMetaFor(detail);
    return (
        <Panel title="Strategies" icon="fa-chess">
            <div className="fi-table-wrap">
                <table className="fi-table">
                    <thead>
                        <tr><th>Strategy</th><th>Kind</th><th>Config</th><th>Model / retrieval</th><th>Repetition</th><th>Portfolio</th></tr>
                    </thead>
                    <tbody>
                        {detail.strategies.map(s => {
                            const m = meta.get(`${s.strategyId}#${s.repetition}`);
                            return (
                                <tr key={`${s.strategyId}#${s.repetition}`}>
                                    <td>{s.label ?? s.strategyId}<div className="fi-small mono">{s.strategyId}</div></td>
                                    <td><KindBadge kind={s.strategyKind} /></td>
                                    <td className="mono fi-small">{s.strategyConfigId}</td>
                                    <td className="fi-small">{m?.modelId ?? m?.provider ?? 'deterministic / not declared'}{m?.retrievalMode ? ` · ${m.retrievalMode}` : ''}</td>
                                    <td className="mono">{s.repetition}</td>
                                    <td><Link to={`/fi/portfolios/${encodeURIComponent(s.portfolioId)}`} className="mono">{s.portfolioId}</Link></td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </Panel>
    );
}

// ─── Replay ─────────────────────────────────────────────────────────────────

function ReplayPanel({ detail }: { detail: RunDetailModel }) {
    const runId = detail.run.runId;
    const [page, setPage] = useState(1);
    const cyclesQuery = useRunCycles(runId, page);
    const cycles = cyclesQuery.data?.items ?? [];
    const [index, setIndex] = useState(0);
    const [playing, setPlaying] = useState(false);
    const [speed, setSpeed] = useState(1);
    const count = cycles.length;
    const current = count === 0 ? 0 : Math.min(index, count - 1);
    const cycle = cycles[current];

    useEffect(() => {
        if (!playing) return;
        const timer = window.setTimeout(() => {
            if (current >= count - 1) setPlaying(false);
            else setIndex(current + 1);
        }, BASE_STEP_MS / speed);
        return () => window.clearTimeout(timer);
    }, [playing, current, count, speed]);

    const goTo = (i: number) => setIndex(Math.max(0, Math.min(count - 1, i)));
    const changePage = (p: number) => {
        setPlaying(false);
        setIndex(0);
        setPage(p);
    };

    return (
        <Panel title="Cycle replay" icon="fa-film">
            <Notice icon="fa-history">
                {detail.run.runType === 'replay' ? 'Accelerated historical playback' : 'Playback'} of <strong>saved</strong> cycles.
                Nothing is re-executed and no model calls are made. The simulation date is the market session being replayed;
                operational time is when the platform processed it.
            </Notice>
            <QueryState query={cyclesQuery} label="cycles" isEmpty={d => d.items.length === 0} emptyMessage="No cycles have been saved for this run yet.">
                {data => (
                    <>
                        <div className="fi-replay-controls" role="toolbar" aria-label="Replay controls">
                            <button onClick={() => goTo(0)} disabled={current === 0} aria-label="First cycle"><i className="fas fa-step-backward"></i></button>
                            <button onClick={() => { setPlaying(false); goTo(current - 1); }} disabled={current === 0} aria-label="Step back"><i className="fas fa-backward"></i></button>
                            <button className="fi-replay-play" onClick={() => setPlaying(p => !p)} disabled={count === 0} aria-label={playing ? 'Pause' : 'Play'}>
                                <i className={`fas ${playing ? 'fa-pause' : 'fa-play'}`}></i> {playing ? 'Pause' : 'Play'}
                            </button>
                            <button onClick={() => { setPlaying(false); goTo(current + 1); }} disabled={current >= count - 1} aria-label="Step forward"><i className="fas fa-forward"></i></button>
                            <button onClick={() => goTo(count - 1)} disabled={current >= count - 1} aria-label="Last cycle"><i className="fas fa-step-forward"></i></button>
                            <label className="fi-inline-label">Speed
                                <select value={speed} onChange={e => setSpeed(Number(e.target.value))}>
                                    {SPEEDS.map(s => <option key={s} value={s}>{s}× ({(BASE_STEP_MS / s / 1000).toFixed(1)} s/cycle)</option>)}
                                </select>
                            </label>
                            <span className="fi-replay-position mono">cycle {cycle?.sequence ?? DASH} · {current + 1}/{count} on this page</span>
                        </div>
                        <input
                            type="range"
                            className="fi-replay-slider"
                            min={0}
                            max={Math.max(0, count - 1)}
                            value={current}
                            onChange={e => { setPlaying(false); goTo(Number(e.target.value)); }}
                            aria-label="Cycle timeline"
                        />
                        <div className="fi-timeline">
                            {cycles.map((c, i) => (
                                <button
                                    key={c.cycleId}
                                    className={`fi-timeline-cell fi-cycle-${c.status} ${i === current ? 'active' : ''}`}
                                    title={`#${c.sequence} ${c.sessionDate} · ${c.status}${c.skipReason ? ` (${c.skipReason})` : ''}`}
                                    onClick={() => { setPlaying(false); goTo(i); }}
                                    aria-label={`Cycle ${c.sequence}, ${c.sessionDate}, ${c.status}`}
                                />
                            ))}
                        </div>
                        <div className="fi-timeline-legend">
                            {['completed', 'skipped', 'failed', 'running', 'pending'].map(s => (
                                <span key={s}><span className={`fi-timeline-cell fi-cycle-${s}`}></span> {s}</span>
                            ))}
                        </div>
                        <Pagination page={data.page} pageSize={data.pageSize} totalCount={data.totalCount} onPage={changePage} label="cycles" />
                        {cycle && <CycleView runId={runId} cycle={cycle} detail={detail} />}
                    </>
                )}
            </QueryState>
        </Panel>
    );
}

function CycleView({ runId, cycle, detail }: { runId: string; cycle: Cycle; detail: RunDetailModel }) {
    const decisionsQuery = useCycleDecisions(runId, cycle.cycleId);
    const decisions = decisionsQuery.data?.items ?? [];
    const missing = detail.strategies.filter(s => !decisions.some(d => d.strategyId === s.strategyId && d.repetition === s.repetition));

    return (
        <div className="fi-cycle">
            <div className="fi-cycle-times">
                <div className="fi-cycle-time fi-cycle-sim">
                    <span className="fi-cycle-time-label"><i className="fas fa-calendar-day"></i> Simulation (market)</span>
                    <div>Session <SessionDate value={cycle.sessionDate} /></div>
                    <div className="fi-small">Decision information cutoff</div>
                    <Instant value={cycle.decisionAsOf} context="market" />
                </div>
                <div className="fi-cycle-time fi-cycle-op">
                    <span className="fi-cycle-time-label"><i className="fas fa-server"></i> Operational (platform)</span>
                    <div className="fi-small">started</div><Instant value={cycle.startedAt} />
                    <div className="fi-small">completed</div><Instant value={cycle.completedAt} />
                </div>
                <div className="fi-cycle-time">
                    <span className="fi-cycle-time-label"><i className="fas fa-database"></i> Frozen inputs</span>
                    <div className="fi-small">status <Tag tone={cycle.status === 'completed' ? 'ok' : cycle.status === 'failed' ? 'fail' : cycle.status === 'skipped' ? 'warn' : 'muted'}>{cycle.status}</Tag></div>
                    {cycle.skipReason && <div className="fi-small fi-warn-text">skip reason: {cycle.skipReason}</div>}
                    <div className="fi-small">{cycle.checkpointed ? 'checkpointed' : 'not checkpointed'} · {cycle.errorCount} error(s) · {cycle.warningCount} warning(s)</div>
                    <div className="fi-small">market snapshot <code className="fi-code">{cycle.marketSnapshotId ?? DASH}</code></div>
                    <div className="fi-small">hash <span className="mono">{shortHash(cycle.marketSnapshotHash)}</span></div>
                    <div className="fi-small">curve {cycle.curveSnapshotId
                        ? <Link to={`/fi/curves/${encodeURIComponent(cycle.curveSnapshotId)}`} className="mono">{cycle.curveSnapshotId}</Link>
                        : DASH}</div>
                </div>
            </div>

            {(cycle.errors ?? []).length > 0 && (
                <>
                    <h3 className="fi-h3">Classified errors for cycle #{cycle.sequence}</h3>
                    <ErrorList errors={cycle.errors ?? []} />
                </>
            )}

            <h3 className="fi-h3">Strategy outcomes for cycle #{cycle.sequence}</h3>
            <QueryState query={decisionsQuery} label="decisions" compact>
                {() => (
                    <div className="fi-table-wrap">
                        <table className="fi-table">
                            <thead>
                                <tr><th>Strategy</th><th>Outcome</th><th>Action</th><th>Reasons / financial consequence</th><th>Integrity</th><th>Completed (operational)</th></tr>
                            </thead>
                            <tbody>
                                {decisions.map(d => <DecisionRow key={d.decisionId} decision={d} />)}
                                {missing.map(s => (
                                    <tr key={`missing-${s.strategyId}#${s.repetition}`} className="fi-row-missing">
                                        <td>{s.label ?? s.strategyId} <span className="fi-small mono">r{s.repetition}</span></td>
                                        <td colSpan={5}><Tag tone="warn"><i className="fas fa-exclamation-circle"></i> no decision recorded for this cycle</Tag></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </QueryState>
        </div>
    );
}

function ErrorList({ errors }: { errors: ClassifiedError[] }) {
    return (
        <div className="fi-table-wrap">
            <table className="fi-table fi-table-dense">
                <thead><tr><th>Scope</th><th>Severity</th><th>Code</th><th>Message</th><th>Strategy / portfolio</th><th>Command / decision</th></tr></thead>
                <tbody>
                    {errors.map((e, i) => (
                        <tr key={`${e.code}-${e.commandId ?? ''}-${i}`}>
                            <td>{humanize(e.scope)}</td>
                            <td><Tag tone={e.severity === 'error' ? 'fail' : 'warn'}>{e.severity}</Tag></td>
                            <td className="mono">{e.code}</td>
                            <td className="fi-small fi-break">{e.message}</td>
                            <td className="fi-small mono">{e.strategyId ?? DASH}{e.portfolioId ? <div>{e.portfolioId}</div> : null}</td>
                            <td className="fi-small mono fi-break">
                                {e.commandId ?? DASH}
                                {e.decisionId && <div><Link to={`/fi/decisions/${encodeURIComponent(e.decisionId)}`}>{e.decisionId}</Link></div>}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function DecisionRow({ decision: d }: { decision: DecisionSummary }) {
    return (
        <tr className={`fi-row-outcome-${outcomeMeta(d.outcome).tone}`}>
            <td>
                <Link to={`/fi/decisions/${encodeURIComponent(d.decisionId)}`}>{d.strategyId}</Link>
                <div className="fi-small mono">r{d.repetition} · {d.strategyKind ?? DASH}</div>
            </td>
            <td><OutcomeBadge outcome={d.outcome} /></td>
            <td className="mono">{d.action ?? DASH}</td>
            <td>
                {d.reasons.length > 0 && <ul className="fi-reasons">{d.reasons.map(r => <li key={r}>{r}</li>)}</ul>}
                <div className="fi-small fi-muted">{outcomeMeta(d.outcome).financial}</div>
            </td>
            <td><Tag tone={d.integrity === 'verified' ? 'ok' : d.integrity === 'synthesized' ? 'muted' : 'fail'} title={INTEGRITY_HINT[d.integrity] ?? d.integrity}>{d.integrity}</Tag></td>
            <td><Instant value={d.completedAt} inline /></td>
        </tr>
    );
}

// ─── Comparison ─────────────────────────────────────────────────────────────

function ComparisonPanel({ runId }: { runId: string }) {
    const query = useRunComparison(runId);
    return (
        <Panel title="Comparison" icon="fa-columns">
            <QueryState query={query} label="run comparison" isEmpty={d => d.entries.length === 0} emptyMessage="No strategy entries yet.">
                {data => <ComparisonTables data={data} />}
            </QueryState>
        </Panel>
    );
}

function ComparisonTables({ data }: { data: RunComparison }) {
    const count = (o: Record<string, number>, k: string) => o[k] ?? 0;
    return (
        <>
            {data.notes.map(n => <p key={n} className="fi-muted-note"><i className="fas fa-info-circle"></i> {n}</p>)}
            <p className="fi-muted-note">
                Group: {data.group.dataMode} · {data.group.riskPolicyId} · {data.group.executionModelId} · {data.group.runType ?? DASH}
                {data.group.startDate ? ` · ${data.group.startDate} → ${data.group.endDate}` : ''}. Metrics are computed by the
                research engine{data.metrics?.metricsVersion ? ` (${data.metrics.metricsVersion})` : ''}; a short window implies no
                statistical significance.
            </p>
            {data.metrics?.status === 'unavailable' && (
                <Notice tone="warn" icon="fa-exclamation-triangle">Evaluation metrics unavailable: {humanize(data.metrics.unavailableReason ?? 'unknown')}</Notice>
            )}
            <h3 className="fi-h3">Financial</h3>
            <div className="fi-table-wrap">
                <table className="fi-table fi-table-dense">
                    <thead>
                        <tr>
                            <th>Strategy</th><th>Latest equity</th><th>Return</th><th>Net / gross</th><th>Annualized</th><th>Sharpe</th>
                            <th>Daily vol.</th><th>Max drawdown</th><th>Turnover</th><th>DV01 avg / max</th><th>Duration avg</th>
                            <th>Coupon income</th><th>Realized / unrealized</th><th>Attribution</th><th>Valuations (incomplete)</th>
                            <th>Fees / spread</th><th>Orders / fills</th><th>Exclusion</th>
                        </tr>
                    </thead>
                    <tbody>
                        {data.entries.map(e => {
                            const m = e.metrics;
                            const reason = m ? m.unavailableReason ?? null : e.metricsUnavailableReason;
                            const na = (r?: string | null) => <span className="fi-unavailable" title={humanize(r ?? reason ?? 'not reported')}>unavailable</span>;
                            return (
                                <tr key={`${e.strategyId}#${e.repetition}`}>
                                    <td><Link to={`/fi/portfolios/${encodeURIComponent(e.portfolioId)}`}>{e.strategyId}</Link> <span className="fi-small mono">r{e.repetition}</span><div><KindBadge kind={e.strategyKind} /></div></td>
                                    <td className="mono">{fmtUsd(e.latestEquityUsd)}</td>
                                    <td className={`mono ${signClass(e.returnRatio)}`}>{fmtPct(e.returnRatio, 3)}</td>
                                    <td className="mono">{m?.netReturn != null ? <>{fmtPct(m.netReturn, 3)} / {fmtPct(m.grossReturn, 3)}</> : na()}</td>
                                    <td className="mono">{m?.annualizedReturn != null ? fmtPct(m.annualizedReturn, 2) : na(m?.annualizedUnavailableReason)}</td>
                                    <td className="mono" title={m?.sharpe?.annualization}>{m?.sharpe?.value != null ? fmtNumber(m.sharpe.value, 2) : na(m?.sharpe?.unavailableReason)}</td>
                                    <td className="mono">{m?.dailyVolatility != null ? fmtPct(m.dailyVolatility, 3) : na()}</td>
                                    <td className="mono">
                                        {m?.drawdown?.maxDrawdown != null
                                            ? <>{fmtPct(m.drawdown.maxDrawdown, 2)}<div className="fi-small">{m.drawdown.maxDrawdown === 0 ? 'none' : m.drawdown.recovered ? `recovery ${m.drawdown.recoveryObservations} obs.` : 'not recovered'}</div></>
                                            : na()}
                                    </td>
                                    <td className="mono">{m?.turnoverRatio != null ? fmtNumber(m.turnoverRatio, 3) : DASH}</td>
                                    <td className="mono">{m?.averageDv01Usd != null ? <>{fmtUsd(m.averageDv01Usd)} / {fmtUsd(m.maxDv01Usd)}</> : DASH}</td>
                                    <td className="mono">{m?.averageEffectiveDurationYears != null ? `${fmtNumber(m.averageEffectiveDurationYears, 2)} y` : DASH}</td>
                                    <td className="mono">{m ? fmtUsd(m.couponIncomeUsd) : DASH}</td>
                                    <td className="mono">{m ? <>{fmtUsd(m.realizedPnlUsd)} / {fmtUsd(m.unrealizedPnlUsd)}</> : DASH}</td>
                                    <td className="mono">
                                        {m?.attribution
                                            ? <span title={`carry ${m.attribution.carryUsd} · price ${m.attribution.priceUsd} · costs ${m.attribution.costsUsd} · residual ${m.attribution.residualUsd}`}>{m.attribution.reconciles ? <Tag tone="ok">reconciles</Tag> : <Tag tone="fail">does not reconcile</Tag>}</span>
                                            : DASH}
                                    </td>
                                    <td className="mono">{e.valuationCount} ({e.incompleteValuationCount})</td>
                                    <td className="mono">{fmtUsd(m?.feesUsd ?? e.feesUsd)} / {fmtUsd(m?.spreadCostUsd ?? e.spreadCostUsd)}</td>
                                    <td className="mono">{e.ordersCreated} / {e.fills}</td>
                                    <td className="fi-small">{e.blockedReason ? `blocked: ${e.blockedReason}` : e.latestEquityUsd === null ? 'no complete valuation' : e.latestValuationComplete === false ? 'latest valuation incomplete' : DASH}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {(data.metrics?.pairedComparisons ?? []).length > 0 && (
                <>
                    <h3 className="fi-h3">Paired differences versus the cash reference</h3>
                    <p className="fi-muted-note">Mean daily return difference with a moving-block bootstrap interval; an uncertainty estimate, not a significance claim.</p>
                    <div className="fi-table-wrap">
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Portfolio</th><th>Versus</th><th>Mean difference</th><th>Interval</th><th>Observations</th><th>Block policy</th></tr></thead>
                            <tbody>
                                {(data.metrics?.pairedComparisons ?? []).map(pc => (
                                    <tr key={`${pc.portfolioId}-${pc.versusPortfolioId}`}>
                                        <td className="mono fi-small">{pc.portfolioId}</td>
                                        <td className="mono fi-small">{pc.versusPortfolioId}</td>
                                        <td className="mono">{pc.available ? fmtPct(pc.meanDifference, 4) : <span className="fi-unavailable" title={humanize(pc.reason)}>unavailable</span>}</td>
                                        <td className="mono">{pc.available ? `${fmtPct(pc.ciLow, 4)} … ${fmtPct(pc.ciHigh, 4)}` : DASH}</td>
                                        <td className="mono">{pc.observations ?? DASH}</td>
                                        <td className="fi-small">{pc.blockPolicy ? `${pc.blockPolicy.method}, block ${pc.blockPolicy.blockLength}, ${pc.blockPolicy.resamples} resamples, seed ${pc.blockPolicy.seed}` : DASH}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </>
            )}

            <h3 className="fi-h3">Evidence</h3>
            <p className="fi-muted-note">Evidence-related outcomes per strategy. Citation-level evidence metrics are inspected per decision.</p>
            <div className="fi-table-wrap">
                <table className="fi-table fi-table-dense">
                    <thead>
                        <tr><th>Strategy</th><th>Decisions</th>{EVIDENCE_OUTCOMES.map(o => <th key={o}><OutcomeBadge outcome={o} /></th>)}<th>Proposals</th><th>Holds</th></tr>
                    </thead>
                    <tbody>
                        {data.entries.map(e => (
                            <tr key={`${e.strategyId}#${e.repetition}`}>
                                <td>{e.strategyId} <span className="fi-small mono">r{e.repetition}</span></td>
                                <td className="mono">{e.decisionCount}</td>
                                {EVIDENCE_OUTCOMES.map(o => <td key={o} className="mono">{count(e.outcomeCounts, o)}</td>)}
                                <td className="mono">{count(e.outcomeCounts, 'completed_proposal')}</td>
                                <td className="mono">{count(e.outcomeCounts, 'completed_hold')}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <h3 className="fi-h3">Operational and usage</h3>
            <p className="fi-muted-note">Model/retrieval costs are estimates under the declared price schedule and are separate from execution costs.</p>
            <div className="fi-table-wrap">
                <table className="fi-table fi-table-dense">
                    <thead>
                        <tr><th>Strategy</th><th>Input tokens</th><th>Output tokens</th><th>Model cost estimate</th><th><OutcomeBadge outcome="failed_budget" /></th><th><OutcomeBadge outcome="failed_invalid_output" /></th><th><OutcomeBadge outcome="skipped_stale_data" /></th><th><OutcomeBadge outcome="cancelled" /></th></tr>
                    </thead>
                    <tbody>
                        {data.entries.map(e => (
                            <tr key={`${e.strategyId}#${e.repetition}`}>
                                <td>{e.strategyId} <span className="fi-small mono">r{e.repetition}</span></td>
                                <td className="mono">{fmtInt(e.inputTokens)}</td>
                                <td className="mono">{fmtInt(e.outputTokens)}</td>
                                <td className="mono">{e.estimatedCostUsd ? fmtUsd(e.estimatedCostUsd, 4) : <span className="fi-muted">not priced</span>}</td>
                                <td className="mono">{count(e.outcomeCounts, 'failed_budget')}</td>
                                <td className="mono">{count(e.outcomeCounts, 'failed_invalid_output')}</td>
                                <td className="mono">{count(e.outcomeCounts, 'skipped_stale_data')}</td>
                                <td className="mono">{count(e.outcomeCounts, 'cancelled')}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <p className="fi-muted-note">Per-decision model calls, tool calls and budget exhaustion are listed on each decision page.</p>
        </>
    );
}

// ─── Decisions list ─────────────────────────────────────────────────────────

function DecisionsPanel({ detail }: { detail: RunDetailModel }) {
    const [page, setPage] = useState(1);
    const [strategyId, setStrategyId] = useState('');
    const [outcome, setOutcome] = useState('');
    const query = useRunDecisions(detail.run.runId, { page, pageSize: 50, strategyId: strategyId || undefined, outcome: outcome || undefined });
    const strategyIds = [...new Set(detail.strategies.map(s => s.strategyId))];
    return (
        <Panel title="All decisions" icon="fa-gavel">
            <div className="fi-filters">
                <label>Strategy
                    <select value={strategyId} onChange={e => { setStrategyId(e.target.value); setPage(1); }}>
                        <option value="">All</option>
                        {strategyIds.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </label>
                <label>Outcome
                    <select value={outcome} onChange={e => { setOutcome(e.target.value); setPage(1); }}>
                        <option value="">All</option>
                        {OUTCOME_ORDER.map(o => <option key={o} value={o}>{outcomeMeta(o).label}</option>)}
                    </select>
                </label>
            </div>
            <QueryState query={query} label="decisions" isEmpty={d => d.items.length === 0} emptyMessage="No decisions match these filters.">
                {data => (
                    <>
                        <div className="fi-table-wrap">
                            <table className="fi-table">
                                <thead>
                                    <tr><th>Strategy</th><th>Outcome</th><th>Action</th><th>Reasons / financial consequence</th><th>Integrity</th><th>Completed (operational)</th></tr>
                                </thead>
                                <tbody>
                                    {data.items.map(d => <DecisionRow key={d.decisionId} decision={d} />)}
                                </tbody>
                            </table>
                        </div>
                        <Pagination page={data.page} pageSize={data.pageSize} totalCount={data.totalCount} onPage={setPage} label="decisions" />
                    </>
                )}
            </QueryState>
        </Panel>
    );
}

function ManifestPanel({ detail }: { detail: RunDetailModel }) {
    return (
        <Panel title="Manifest" icon="fa-file-signature" id="manifest">
            <KeyValueGrid
                columns={4}
                items={[
                    { label: 'Manifest hash', value: <span className="mono fi-break">{detail.manifestHash}</span> },
                    { label: 'Spec version', value: manifestValue(detail, 'specVersion') },
                    { label: 'Git commit', value: <span className="mono">{manifestValue(detail, 'gitCommit') ?? DASH}</span> },
                    { label: 'Config hash', value: <span className="mono">{shortHash(manifestValue(detail, 'configHash'))}</span> },
                    { label: 'Universe version', value: manifestValue(detail, 'universeVersion') },
                    { label: 'Information policy', value: manifestValue(detail, 'informationPolicy') },
                    { label: 'Window', value: detail.run.startDate ? `${detail.run.startDate} → ${detail.run.endDate}` : manifestValue(detail, 'startDate') ? `${manifestValue(detail, 'startDate')} → ${manifestValue(detail, 'endDate')}` : undefined },
                    { label: 'Manifest status', value: manifestValue(detail, 'status') },
                ]}
            />
            {detail.manifest === null
                ? <p className="fi-muted-note">The manifest body is not available.</p>
                : <JsonDetails value={detail.manifest} summary="Full immutable manifest (JSON)" />}
        </Panel>
    );
}
