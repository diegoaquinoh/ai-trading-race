import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
    useCreateExperiment,
    useExperimentComparison,
    useExperiments,
    usePortfolios,
    useRunDetails,
    useRuns,
    useStartRun,
    useValuationSeries,
} from '../api/hooks';
import type { ComparisonEntry, ComparisonGroupKey, JsonObject, Portfolio, ResponseMode, RunComparison, RunDetail, RunSummary, RunType } from '../api/types';
import { DataModeBadge, JobStateBadge, KindBadge, OutcomeBadge, ResponseModeBadge, Tag } from '../components/Badges';
import { EquityCurves } from '../components/EquityCurves';
import type { EquitySeries } from '../components/EquityCurves';
import { Instant, TimeLegend } from '../components/Instant';
import { Notice, PageHeader, Panel } from '../components/Layout';
import { Pagination } from '../components/Pagination';
import { InlineError, QueryState } from '../components/States';
import {
    FAILURE_OUTCOMES,
    JOB_STATES,
    OUTCOME_ORDER,
    SERIES_COLORS,
    STRATEGY_KIND_ORDER,
    kindMeta,
} from '../lib/domain';
import { DASH, fmtInt, fmtNumber, fmtPct, fmtUsd, humanize, shortHash, signClass } from '../lib/format';
import { strategyMetaFor } from '../lib/runMeta';
import type { StrategyMeta } from '../lib/runMeta';

const MIN_SHARPE_RETURNS = 60;

export function ExperimentsOverview() {
    const [filter, setFilter] = useState({ dataMode: '', runType: '', jobState: '', experimentId: '' });
    const [page, setPage] = useState(1);
    const runsQuery = useRuns({ ...filter, page, pageSize: 20 });
    const experimentsQuery = useExperiments(1, 200);
    const [chosenExperiment, setChosenExperiment] = useState('');
    const experimentId = chosenExperiment
        || filter.experimentId
        || experimentsQuery.data?.items[0]?.experimentId
        || runsQuery.data?.items[0]?.experimentId
        || '';

    const updateFilter = (key: keyof typeof filter, value: string) => {
        setFilter(prev => ({ ...prev, [key]: value }));
        setPage(1);
    };

    return (
        <div className="fi-page">
            <PageHeader
                icon="fa-flask"
                title="Fixed income research lab"
                subtitle="Controlled experiments comparing cash references, quantitative policies, single agents and specialist teams on USD fixed-rate notes. Results are research outputs, not performance claims."
            />
            <TimeLegend />

            <Panel title="Runs" icon="fa-list">
                <div className="fi-filters">
                    <label>Experiment
                        <select value={filter.experimentId} onChange={e => updateFilter('experimentId', e.target.value)}>
                            <option value="">All</option>
                            {(experimentsQuery.data?.items ?? []).map(x => (
                                <option key={`${x.experimentId}@${x.version}`} value={x.experimentId}>{x.experimentId} (v{x.version})</option>
                            ))}
                        </select>
                    </label>
                    <label>Data mode
                        <select value={filter.dataMode} onChange={e => updateFilter('dataMode', e.target.value)}>
                            <option value="">All</option>
                            <option value="synthetic_curve">Synthetic curve</option>
                            <option value="observed_security">Observed security</option>
                        </select>
                    </label>
                    <label>Run type
                        <select value={filter.runType} onChange={e => updateFilter('runType', e.target.value)}>
                            <option value="">All</option>
                            <option value="replay">Historical replay</option>
                            <option value="forward">Forward paper cycle</option>
                        </select>
                    </label>
                    <label>Job state
                        <select value={filter.jobState} onChange={e => updateFilter('jobState', e.target.value)}>
                            <option value="">All</option>
                            {JOB_STATES.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                    </label>
                </div>
                <QueryState
                    query={runsQuery}
                    label="runs"
                    isEmpty={d => d.items.length === 0}
                    emptyMessage="No runs match these filters. Operators can start a run below."
                >
                    {data => (
                        <>
                            <RunsTable runs={data.items} />
                            <Pagination page={data.page} pageSize={data.pageSize} totalCount={data.totalCount} onPage={setPage} label="runs" />
                        </>
                    )}
                </QueryState>
            </Panel>

            <Panel
                title="Leaderboard and comparison"
                icon="fa-trophy"
                actions={
                    <label className="fi-inline-label">Experiment
                        <select value={experimentId} onChange={e => setChosenExperiment(e.target.value)}>
                            {experimentId === '' && <option value="">None</option>}
                            {[...new Set((experimentsQuery.data?.items ?? []).map(x => x.experimentId))].map(id => (
                                <option key={id} value={id}>{id}</option>
                            ))}
                            {experimentId && !(experimentsQuery.data?.items ?? []).some(x => x.experimentId === experimentId) && (
                                <option value={experimentId}>{experimentId}</option>
                            )}
                        </select>
                    </label>
                }
            >
                {experimentId
                    ? <ComparisonSection experimentId={experimentId} />
                    : <p className="fi-muted-note">No experiment registered yet.</p>}
            </Panel>

            <OperatorPanel experimentIds={[...new Set((experimentsQuery.data?.items ?? []).map(x => x.experimentId))]} defaultExperiment={experimentId} />
        </div>
    );
}

// ─── Runs table ─────────────────────────────────────────────────────────────

function RunsTable({ runs }: { runs: RunSummary[] }) {
    const details = useRunDetails(runs.map(r => r.runId));
    return (
        <div className="fi-table-wrap">
            <table className="fi-table">
                <thead>
                    <tr>
                        <th>Run</th>
                        <th>Data mode</th>
                        <th>Type / responses</th>
                        <th>Progress</th>
                        <th title="Simulation clock of the replay (market time)">Simulated clock</th>
                        <th title="Platform processing time">Operational time</th>
                        <th>Policy / execution</th>
                        <th>Model and config versions</th>
                        <th>Manifest</th>
                    </tr>
                </thead>
                <tbody>
                    {runs.map((run, i) => {
                        const detail = details[i]?.data;
                        const meta = [...strategyMetaFor(detail).values()];
                        const models = [...new Set(meta.map(m => m.modelId ?? m.provider).filter(Boolean))];
                        const configs = [...new Set(meta.map(m => m.configId))];
                        return (
                            <tr key={run.runId}>
                                <td>
                                    <Link to={`/fi/runs/${encodeURIComponent(run.runId)}`} className="mono">{run.runId}</Link>
                                    <div className="fi-small">{run.experimentId} v{run.experimentVersion}</div>
                                    {run.startDate && <div className="fi-small" title="Evaluation window">{run.startDate} → {run.endDate}</div>}
                                </td>
                                <td><DataModeBadge mode={run.dataMode} label={run.dataModeLabel} /></td>
                                <td>
                                    <div>{run.runType === 'replay' ? 'Historical replay' : run.runType === 'forward' ? 'Forward paper cycle' : run.runType}</div>
                                    <ResponseModeBadge mode={run.responseMode} />
                                </td>
                                <td>
                                    <JobStateBadge state={run.jobState} />
                                    <div className="fi-small">{run.completedCycles}/{run.totalCycles ?? '?'} cycles</div>
                                    {run.checkpoint && <div className="fi-small" title={`Last checkpoint ${run.checkpoint.cycleId}`}>checkpoint #{run.checkpoint.sequence}</div>}
                                    {run.errors && (run.errors.runErrors + run.errors.cycleErrors) > 0 && (
                                        <div className="fi-small fi-fail-text" title={Object.entries(run.errors.byScope).map(([k, v]) => `${k}: ${v}`).join('\n')}>
                                            {run.errors.runErrors + run.errors.cycleErrors} error(s)
                                        </div>
                                    )}
                                    {run.statusReason && <div className="fi-small fi-warn-text">{run.statusReason}</div>}
                                </td>
                                <td><Instant value={run.simulatedClock} context="market" /></td>
                                <td>
                                    <div className="fi-small">created</div><Instant value={run.createdAt} />
                                    {run.completedAt && <><div className="fi-small">completed</div><Instant value={run.completedAt} /></>}
                                </td>
                                <td>
                                    <div className="mono fi-small">{run.riskPolicyId}</div>
                                    <div className="mono fi-small">{run.executionModelId}</div>
                                </td>
                                <td>
                                    {details[i]?.isLoading && <span className="fi-small">loading…</span>}
                                    {detail && (
                                        <>
                                            <div className="fi-small">engine {detail.engineVersion ?? DASH}</div>
                                            <div className="fi-small">models: {models.length ? models.join(', ') : 'none (deterministic)'}</div>
                                            <div className="fi-small" title={configs.join('\n')}>{configs.length} strategy configs</div>
                                        </>
                                    )}
                                </td>
                                <td>
                                    <Link to={`/fi/runs/${encodeURIComponent(run.runId)}#manifest`} className="fi-small">
                                        <i className="fas fa-file-signature"></i> {shortHash(run.manifestHash ?? detail?.manifestHash, 8)}
                                    </Link>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

// ─── Comparison ─────────────────────────────────────────────────────────────

interface Row {
    key: string;
    entry: ComparisonEntry;
    run: RunComparison;
    detail?: RunDetail;
    meta?: StrategyMeta;
    architecture: string;
    color: string;
}

interface CompatGroup {
    key: string;
    group: ComparisonGroupKey;
    dataModeLabel: string;
    runType: string;
    window: string;
    notes: string[];
    rows: Row[];
}

function ComparisonSection({ experimentId }: { experimentId: string }) {
    const comparison = useExperimentComparison(experimentId);
    const runs = (comparison.data?.groups ?? []).flatMap(g => g.runs);
    const details = useRunDetails(runs.map(r => r.runId));
    const detailById = new Map(runs.map((r, i) => [r.runId, details[i]?.data]));
    const windowFor = (key: ComparisonGroupKey) =>
        key.startDate && key.endDate ? `${key.startDate} → ${key.endDate}` : 'window not declared';

    const [filters, setFilters] = useState({ repetition: '', architecture: '', family: '', riskPolicy: '', execution: '' });
    const [groupKey, setGroupKey] = useState('');

    // Compatibility groups come from the API (data mode, risk policy, execution model, run type and
    // evaluation window); runs are never ranked across groups.
    let colorIndex = 0;
    const groups = new Map<string, CompatGroup>();
    for (const apiGroup of comparison.data?.groups ?? []) {
        for (const run of apiGroup.runs) {
            const detail = detailById.get(run.runId);
            const metaMap = strategyMetaFor(detail);
            const runType = apiGroup.group.runType ?? detail?.run.runType ?? 'unknown';
            const window = windowFor(apiGroup.group);
            const key = [apiGroup.group.dataMode, apiGroup.group.riskPolicyId, apiGroup.group.executionModelId, runType, window].join('|');
            let g = groups.get(key);
            if (!g) {
                g = { key, group: apiGroup.group, dataModeLabel: apiGroup.dataModeLabel, runType, window, notes: [], rows: [] };
                groups.set(key, g);
            }
            for (const note of run.notes) if (!g.notes.includes(note)) g.notes.push(note);
            for (const entry of run.entries) {
                const meta = metaMap.get(`${entry.strategyId}#${entry.repetition}`);
                const retrieval = meta?.retrievalMode && meta.retrievalMode !== 'none' ? ` · ${meta.retrievalMode}` : '';
                g.rows.push({
                    key: `${run.runId}/${entry.strategyId}#${entry.repetition}`,
                    entry,
                    run,
                    detail,
                    meta,
                    architecture: `${kindMeta(entry.strategyKind).label}${retrieval}`,
                    color: SERIES_COLORS[colorIndex++ % SERIES_COLORS.length],
                });
            }
        }
    }
    const groupList = [...groups.values()];
    const allRows = groupList.flatMap(g => g.rows);
    const options = {
        repetition: [...new Set(allRows.map(r => String(r.entry.repetition)))].sort(),
        architecture: [...new Set(allRows.map(r => r.architecture))].sort(),
        family: [...new Set(allRows.map(r => r.meta?.family ?? 'unspecified'))].sort(),
        riskPolicy: [...new Set(groupList.map(g => g.group.riskPolicyId))].sort(),
        execution: [...new Set(groupList.map(g => g.group.executionModelId))].sort(),
    };
    const visibleGroups = groupList.filter(g =>
        (!filters.riskPolicy || g.group.riskPolicyId === filters.riskPolicy)
        && (!filters.execution || g.group.executionModelId === filters.execution));
    const active = visibleGroups.find(g => g.key === groupKey) ?? visibleGroups[0];
    const rows = (active?.rows ?? []).filter(r =>
        (!filters.repetition || String(r.entry.repetition) === filters.repetition)
        && (!filters.architecture || r.architecture === filters.architecture)
        && (!filters.family || (r.meta?.family ?? 'unspecified') === filters.family));

    return (
        <QueryState
            query={comparison}
            label="experiment comparison"
            isEmpty={d => d.groups.length === 0}
            emptyMessage={comparison.data?.notes.join(' ') || 'No runs have been compared for this experiment yet.'}
        >
            {data => (
                <>
                    {data.notes.map(n => <Notice key={n}>{n}</Notice>)}
                    {groupList.length > 1 && (
                        <Notice tone="warn" icon="fa-layer-group">
                            {groupList.length} compatibility groups differ in data mode, cost/execution policy, risk policy, run type or
                            evaluation window. They are shown separately and are never ranked against each other.
                        </Notice>
                    )}
                    <div className="fi-filters">
                        <FilterSelect label="Repetition" value={filters.repetition} options={options.repetition} onChange={v => setFilters(f => ({ ...f, repetition: v }))} />
                        <FilterSelect label="Architecture" value={filters.architecture} options={options.architecture} onChange={v => setFilters(f => ({ ...f, architecture: v }))} />
                        <FilterSelect label="Model family" value={filters.family} options={options.family} onChange={v => setFilters(f => ({ ...f, family: v }))} />
                        <FilterSelect label="Risk policy" value={filters.riskPolicy} options={options.riskPolicy} onChange={v => setFilters(f => ({ ...f, riskPolicy: v }))} />
                        <FilterSelect label="Execution assumptions" value={filters.execution} options={options.execution} onChange={v => setFilters(f => ({ ...f, execution: v }))} />
                    </div>
                    {visibleGroups.length > 1 && (
                        <div className="fi-tabs" role="tablist">
                            {visibleGroups.map(g => (
                                <button key={g.key} role="tab" aria-selected={g === active} className={g === active ? 'active' : ''} onClick={() => setGroupKey(g.key)}>
                                    {g.group.dataMode === 'synthetic_curve' ? 'Synthetic' : 'Observed'} · {g.group.executionModelId} · {g.runType} · {g.window}
                                </button>
                            ))}
                        </div>
                    )}
                    {active ? <GroupView group={active} rows={rows} /> : <p className="fi-muted-note">No group matches the filters.</p>}
                </>
            )}
        </QueryState>
    );
}

function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
    return (
        <label>{label}
            <select value={value} onChange={e => onChange(e.target.value)}>
                <option value="">All</option>
                {options.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
        </label>
    );
}

function returnSortValue(entry: ComparisonEntry): number {
    // Sorting only (display order); the return itself is computed by the API.
    return entry.returnRatio === null ? Number.NEGATIVE_INFINITY : Number(entry.returnRatio);
}

function exclusionReasons(entry: ComparisonEntry, portfolio: Portfolio | undefined): string[] {
    const reasons: string[] = [];
    if (entry.blockedReason) reasons.push(`portfolio blocked: ${entry.blockedReason}`);
    if (entry.latestEquityUsd === null) reasons.push('no complete valuation: excluded from ranking');
    if (entry.latestValuationComplete === false) reasons.push('latest valuation incomplete (return uses last complete one)');
    for (const r of portfolio?.latestValuation?.incompleteReasons ?? []) reasons.push(r);
    return reasons;
}

function GroupView({ group, rows }: { group: CompatGroup; rows: Row[] }) {
    const portfolioQueries = usePortfolios(rows.map(r => r.entry.portfolioId));
    const portfolioById = new Map(rows.map((r, i) => [r.entry.portfolioId, portfolioQueries[i]?.data]));
    const chartRows = rows.slice(0, SERIES_COLORS.length);
    const valuationQueries = useValuationSeries(chartRows.map(r => r.entry.portfolioId));
    const series: EquitySeries[] = chartRows.map((r, i) => ({
        key: r.key,
        label: `${r.meta?.label ?? r.entry.strategyId}${r.entry.repetition ? ` r${r.entry.repetition}` : ''}`,
        color: r.color,
        valuations: valuationQueries[i]?.data?.items ?? [],
    }));
    const maxObservations = Math.max(0, ...rows.map(r => r.entry.metrics?.observationCount ?? r.entry.valuationCount));
    const shortWindow = maxObservations < MIN_SHARPE_RETURNS;

    const byKind = STRATEGY_KIND_ORDER
        .map(kind => ({ kind, rows: rows.filter(r => r.entry.strategyKind === kind) }))
        .concat([{ kind: 'other', rows: rows.filter(r => !STRATEGY_KIND_ORDER.includes(r.entry.strategyKind)) }])
        .filter(k => k.rows.length > 0);

    return (
        <div className="fi-group">
            <div className="fi-group-head">
                <DataModeBadge mode={group.group.dataMode} label={group.dataModeLabel} />
                <Tag tone="muted" title="Risk policy">{group.group.riskPolicyId}</Tag>
                <Tag tone="muted" title="Execution and cost assumptions">{group.group.executionModelId}</Tag>
                <Tag tone="muted" title="Run type">{group.runType}</Tag>
                <Tag tone="muted" title="Evaluation window">{group.window}</Tag>
            </div>
            {group.notes.map(n => <p key={n} className="fi-muted-note"><i className="fas fa-info-circle"></i> {n}</p>)}
            {shortWindow && (
                <Notice tone="warn" icon="fa-hourglass-half">
                    Short evaluation window ({maxObservations} daily returns). No statistical significance is implied by this
                    ordering; the research engine reports Sharpe only with at least {MIN_SHARPE_RETURNS} daily returns, non-zero
                    variance and a declared risk-free series, and states the reason otherwise.
                </Notice>
            )}

            <div className="fi-split">
                <div className="fi-split-main">
                    {byKind.map(({ kind, rows: kindRows }) => (
                        <LeaderboardTable key={kind} kind={kind} rows={kindRows} portfolioById={portfolioById} />
                    ))}
                </div>
                <div className="fi-split-side">
                    <h3 className="fi-h3">Equity curves (reconciled NAV)</h3>
                    {rows.length > SERIES_COLORS.length && (
                        <p className="fi-muted-note">Showing the first {SERIES_COLORS.length} of {rows.length} portfolios; filter to compare others.</p>
                    )}
                    {valuationQueries.some(q => q.isLoading) ? <p className="fi-muted-note">Loading valuations…</p> : <EquityCurves series={series} height={280} />}
                    {group.group.dataMode === 'synthetic_curve' && (
                        <p className="fi-muted-note">Synthetic mode: equity is marked with curve-model prices, not market quotes.</p>
                    )}
                </div>
            </div>

            <RiskCostFailureTable rows={rows} portfolioById={portfolioById} />
        </div>
    );
}

function LeaderboardTable({ kind, rows, portfolioById }: { kind: string; rows: Row[]; portfolioById: Map<string, Portfolio | undefined> }) {
    const meta = kindMeta(kind);
    const sorted = [...rows].sort((a, b) => returnSortValue(b.entry) - returnSortValue(a.entry));
    const isRanked = (r: Row) => r.entry.latestEquityUsd !== null && !r.entry.blockedReason;
    const ranks = new Map<string, number>();
    sorted.filter(isRanked).forEach((r, i) => ranks.set(r.key, i + 1));
    return (
        <div className="fi-kind-section">
            <h3 className="fi-h3"><KindBadge kind={kind} /> {meta.plural} <span className="fi-muted fi-small">{meta.description}</span></h3>
            <div className="fi-table-wrap">
                <table className="fi-table">
                    <thead>
                        <tr>
                            <th title="Rank within this strategy class and compatibility group only">#</th>
                            <th>Strategy</th>
                            <th>Latest equity</th>
                            <th>Return</th>
                            <th title="Net of execution costs / gross of spread and fees (engine metrics-v1)">Net / gross</th>
                            <th>Sharpe</th>
                            <th>Valuations</th>
                            <th>Exclusions / badges</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sorted.map(r => {
                            const reasons = exclusionReasons(r.entry, portfolioById.get(r.entry.portfolioId));
                            const rank = ranks.get(r.key);
                            const m = r.entry.metrics;
                            const sharpe = m?.sharpe;
                            return (
                                <tr key={r.key}>
                                    <td className="mono">{rank ?? DASH}</td>
                                    <td>
                                        <span className="fi-swatch" style={{ background: r.color }} aria-hidden="true"></span>
                                        <Link to={`/fi/portfolios/${encodeURIComponent(r.entry.portfolioId)}`}>{r.meta?.label ?? r.entry.strategyId}</Link>
                                        <div className="fi-small mono">{r.entry.strategyId} · rep {r.entry.repetition} · {r.architecture}</div>
                                        <div className="fi-small">
                                            <Link to={`/fi/runs/${encodeURIComponent(r.run.runId)}`}>{r.run.runId}</Link>
                                            {r.meta?.modelId && <> · {r.meta.modelId}</>}
                                        </div>
                                    </td>
                                    <td className="mono">
                                        {fmtUsd(r.entry.latestEquityUsd)}
                                        <div className="fi-small">initial {fmtUsd(r.entry.initialCapitalUsd, 0)}</div>
                                    </td>
                                    <td className={`mono ${signClass(r.entry.returnRatio)}`}>{fmtPct(r.entry.returnRatio, 3)}</td>
                                    <td className="mono">
                                        {m ? <>{fmtPct(m.netReturn, 3)} / {fmtPct(m.grossReturn, 3)}</> : <Unavailable reason={r.entry.metricsUnavailableReason} />}
                                    </td>
                                    <td className="mono" title={sharpe?.annualization}>
                                        {sharpe?.value != null
                                            ? fmtNumber(sharpe.value, 2)
                                            : <Unavailable reason={sharpe?.unavailableReason ?? m?.unavailableReason ?? r.entry.metricsUnavailableReason} />}
                                    </td>
                                    <td>
                                        {r.entry.latestValuationComplete === false
                                            ? <Tag tone="warn">latest incomplete</Tag>
                                            : r.entry.latestValuationAt ? <Tag tone="ok">complete</Tag> : <Tag tone="fail">missing</Tag>}
                                        <div className="fi-small">{r.entry.valuationCount} total · {r.entry.incompleteValuationCount} incomplete</div>
                                        {r.entry.latestValuationAt && <Instant value={r.entry.latestValuationAt} context="market" inline />}
                                    </td>
                                    <td>{reasons.length === 0 ? <span className="fi-muted">none</span> : (
                                        <ul className="fi-reasons">{reasons.map(x => <li key={x}>{x}</li>)}</ul>
                                    )}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function Unavailable({ reason }: { reason?: string | null }) {
    return <span className="fi-unavailable" title={humanize(reason ?? 'not reported')}>unavailable</span>;
}

function RiskCostFailureTable({ rows, portfolioById }: { rows: Row[]; portfolioById: Map<string, Portfolio | undefined> }) {
    if (rows.length === 0) return null;
    return (
        <div className="fi-kind-section">
            <h3 className="fi-h3"><i className="fas fa-balance-scale"></i> Risk, cost and failure metrics</h3>
            <p className="fi-muted-note">
                Computed by the research engine (metrics-v1) from each portfolio's saved valuations, fills and cash flows;
                incomplete valuations are counted and excluded. Financial execution costs (fees, spread) are reported
                separately from model/retrieval cost estimates. Actual DV01 and duration exposure differ even under equal limits.
            </p>
            <div className="fi-table-wrap">
                <table className="fi-table fi-table-dense">
                    <thead>
                        <tr>
                            <th>Strategy</th>
                            <th title="Average / maximum parallel DV01 over complete valuations">DV01 avg / max (USD/bp)</th>
                            <th title="Average / latest effective duration">Eff. duration avg / end</th>
                            <th title="Standard deviation of daily returns">Daily vol.</th>
                            <th>Max drawdown (recovery)</th>
                            <th>Annualized</th>
                            <th title="Traded consideration / average NAV">Turnover</th>
                            <th>Fees / spread</th>
                            <th>Coupon income</th>
                            <th>Realized / unrealized</th>
                            <th title="carry + price + costs + residual = total PnL">Attribution</th>
                            <th>Orders / fills / expiries</th>
                            <th>Model cost est.</th>
                            <th>Tokens in / out</th>
                            <th>Decisions</th>
                            <th>Outcomes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map(r => {
                            const latest = portfolioById.get(r.entry.portfolioId)?.latestValuation;
                            const failures = FAILURE_OUTCOMES.reduce((n, o) => n + (r.entry.outcomeCounts[o] ?? 0), 0);
                            const m = r.entry.metrics;
                            const missing = m ? m.unavailableReason ?? null : r.entry.metricsUnavailableReason;
                            const dd = m?.drawdown;
                            const att = m?.attribution;
                            return (
                                <tr key={r.key}>
                                    <td>
                                        <span className="fi-swatch" style={{ background: r.color }} aria-hidden="true"></span>
                                        {r.meta?.label ?? r.entry.strategyId} <span className="fi-small mono">r{r.entry.repetition}</span>
                                        {missing && <div className="fi-small fi-warn-text">metrics: {humanize(missing)}</div>}
                                    </td>
                                    <td className="mono">
                                        {m?.averageDv01Usd != null ? <>{fmtUsd(m.averageDv01Usd)} / {fmtUsd(m.maxDv01Usd)}</> : latest ? fmtUsd(latest.parallelDv01Usd) : DASH}
                                    </td>
                                    <td className="mono">
                                        {m?.averageEffectiveDurationYears != null
                                            ? `${fmtNumber(m.averageEffectiveDurationYears, 2)} / ${fmtNumber(m.endEffectiveDurationYears, 2)} y`
                                            : latest?.effectiveDurationYears ? `${fmtNumber(latest.effectiveDurationYears, 2)} y` : DASH}
                                    </td>
                                    <td className="mono">{m?.dailyVolatility != null ? fmtPct(m.dailyVolatility, 3) : <Unavailable reason={missing ?? 'fewer_than_2_returns'} />}</td>
                                    <td className="mono">
                                        {dd?.maxDrawdown != null ? (
                                            <>
                                                {fmtPct(dd.maxDrawdown, 2)}
                                                <div className="fi-small">
                                                    {dd.maxDrawdown === 0 ? 'no drawdown' : dd.recovered ? `recovered in ${dd.recoveryObservations} obs.` : 'not recovered'}
                                                </div>
                                            </>
                                        ) : <Unavailable reason={missing} />}
                                    </td>
                                    <td className="mono">{m?.annualizedReturn != null ? fmtPct(m.annualizedReturn, 2) : <Unavailable reason={m?.annualizedUnavailableReason ?? missing} />}</td>
                                    <td className="mono">{m?.turnoverRatio != null ? fmtNumber(m.turnoverRatio, 3) : DASH}</td>
                                    <td className="mono">{fmtUsd(m?.feesUsd ?? r.entry.feesUsd)} / {fmtUsd(m?.spreadCostUsd ?? r.entry.spreadCostUsd)}</td>
                                    <td className="mono">{m ? fmtUsd(m.couponIncomeUsd) : DASH}</td>
                                    <td className="mono">{m ? <>{fmtUsd(m.realizedPnlUsd)} / {fmtUsd(m.unrealizedPnlUsd)}</> : DASH}</td>
                                    <td className="mono">
                                        {att ? (
                                            <span title={`carry ${att.carryUsd} · price ${att.priceUsd} · costs ${att.costsUsd} · residual ${att.residualUsd}`}>
                                                {att.reconciles ? <Tag tone="ok">reconciles</Tag> : <Tag tone="fail">does not reconcile</Tag>}
                                                <div className="fi-small">residual {fmtUsd(att.residualUsd)}</div>
                                            </span>
                                        ) : DASH}
                                    </td>
                                    <td className="mono">{r.entry.ordersCreated} / {r.entry.fills} / {m?.expiryCount ?? DASH}</td>
                                    <td className="mono">{r.entry.estimatedCostUsd ? fmtUsd(r.entry.estimatedCostUsd, 4) : <span className="fi-muted">not priced</span>}</td>
                                    <td className="mono">{fmtInt(r.entry.inputTokens)} / {fmtInt(r.entry.outputTokens)}</td>
                                    <td className="mono">
                                        {r.entry.decisionCount}
                                        {failures > 0 && <div className="fi-fail-text fi-small">{failures} failed</div>}
                                    </td>
                                    <td>
                                        <div className="fi-outcome-counts">
                                            {OUTCOME_ORDER.filter(o => r.entry.outcomeCounts[o]).map(o => (
                                                <span key={o} className="fi-outcome-count"><OutcomeBadge outcome={o} compact /> {r.entry.outcomeCounts[o]}</span>
                                            ))}
                                            {Object.keys(r.entry.outcomeCounts).length === 0 && <span className="fi-muted">none</span>}
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

// ─── Operator actions ───────────────────────────────────────────────────────

function OperatorPanel({ experimentIds, defaultExperiment }: { experimentIds: string[]; defaultExperiment: string }) {
    const startRun = useStartRun();
    const createExperiment = useCreateExperiment();
    const [experimentId, setExperimentId] = useState('');
    const [runType, setRunType] = useState<RunType>('replay');
    const [responseMode, setResponseMode] = useState<ResponseMode>('recorded_replay');
    const [definitionText, setDefinitionText] = useState('');
    const [parseError, setParseError] = useState<string | null>(null);
    const target = experimentId || defaultExperiment;

    const register = () => {
        setParseError(null);
        let parsed: unknown;
        try {
            parsed = JSON.parse(definitionText);
        } catch (e) {
            setParseError(`Invalid JSON: ${(e as Error).message}`);
            return;
        }
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            setParseError('The definition must be a JSON object.');
            return;
        }
        createExperiment.mutate(parsed as JsonObject);
    };

    return (
        <Panel title="Operator actions" icon="fa-user-cog">
            <p className="fi-muted-note">
                Requires the Operator role; the server rejects other users with 401/403. Runs execute asynchronously and
                return a job status link.
            </p>
            <div className="fi-operator-grid">
                <div>
                    <h3 className="fi-h3">Start a run</h3>
                    <div className="fi-filters">
                        <label>Experiment
                            <select value={target} onChange={e => setExperimentId(e.target.value)}>
                                {target === '' && <option value="">None</option>}
                                {experimentIds.map(id => <option key={id} value={id}>{id}</option>)}
                            </select>
                        </label>
                        <label>Run type
                            <select value={runType} onChange={e => setRunType(e.target.value as RunType)}>
                                <option value="replay">Historical replay</option>
                                <option value="forward">Forward paper cycle</option>
                            </select>
                        </label>
                        <label>Responses
                            <select value={responseMode} onChange={e => setResponseMode(e.target.value as ResponseMode)}>
                                <option value="recorded_replay">Recorded replay (no new model calls)</option>
                                <option value="fresh_inference">Fresh inference</option>
                            </select>
                        </label>
                    </div>
                    <button className="fi-button" disabled={!target || startRun.isPending}
                        onClick={() => startRun.mutate({ experimentId: target, request: { runType, responseMode } })}>
                        <i className={`fas ${startRun.isPending ? 'fa-spinner fa-spin' : 'fa-play'}`}></i> Start run
                    </button>
                    <InlineError error={startRun.error} />
                    {startRun.data && (
                        <p className="fi-operator-result">
                            <i className="fas fa-check"></i> {startRun.data.alreadyExisted ? 'Run already existed' : 'Run accepted'}:{' '}
                            <Link to={`/fi/runs/${encodeURIComponent(startRun.data.runId)}`}>{startRun.data.runId}</Link> ({startRun.data.jobState})
                        </p>
                    )}
                </div>
                <div>
                    <h3 className="fi-h3">Register an immutable experiment definition</h3>
                    <textarea
                        className="fi-textarea mono"
                        rows={6}
                        placeholder='{"experimentId": "...", "version": 1, "name": "...", "startDate": "YYYY-MM-DD", "endDate": "YYYY-MM-DD", "instrumentUniverseVersion": "...", "strategies": [...]}'
                        value={definitionText}
                        onChange={e => setDefinitionText(e.target.value)}
                    />
                    <button className="fi-button" disabled={!definitionText.trim() || createExperiment.isPending} onClick={register}>
                        <i className={`fas ${createExperiment.isPending ? 'fa-spinner fa-spin' : 'fa-save'}`}></i> Validate and register
                    </button>
                    {parseError && <p className="fi-inline-error">{parseError}</p>}
                    <InlineError error={createExperiment.error} />
                    {createExperiment.data && (
                        <p className="fi-operator-result">
                            <i className="fas fa-check"></i> Registered {createExperiment.data.experimentId} v{createExperiment.data.version}{' '}
                            <span className="mono fi-small">{shortHash(createExperiment.data.definitionHash)}</span>
                        </p>
                    )}
                </div>
            </div>
        </Panel>
    );
}
