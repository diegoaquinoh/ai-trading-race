import { useState } from 'react';
import { Link } from 'react-router-dom';
import { fiApi, getAccessToken, setAccessToken } from '../api/client';
import { useAdminJob, useFailedRuns, useHealth } from '../api/hooks';
import type { FixedIncomeHealth, JsonObject, ResponseMode } from '../api/types';
import { JobStateBadge, PassFail, Tag } from '../components/Badges';
import { Instant, TimeLegend } from '../components/Instant';
import { JsonDetails, Notice, PageHeader, Panel } from '../components/Layout';
import { OperatorAction } from '../components/OperatorAction';
import { QueryState } from '../components/States';
import { DASH, humanize } from '../lib/format';
import { asArray, asObject, pick, pickBool, pickStr } from '../lib/read';

export function HealthPage() {
    const health = useHealth();
    return (
        <div className="fi-page">
            <PageHeader icon="fa-heartbeat" title="Platform health" breadcrumbs={[{ to: '/fi', label: 'Research lab' }]}
                subtitle="Ingestion freshness, READY manifests and index builds, coverage, failed jobs, dependency readiness and usage against budget." />
            <TimeLegend />
            <QueryState query={health} label="health report">
                {report => <HealthBody report={report} />}
            </QueryState>
            <FailedRunsPanel />
            <OperatorPanel />
        </div>
    );
}

function statusTone(status: string): 'ok' | 'warn' | 'fail' {
    return status === 'ready' ? 'ok' : status === 'degraded' ? 'warn' : 'fail';
}

function HealthBody({ report }: { report: FixedIncomeHealth }) {
    const caps = report.researchEngine.capabilities ?? {};
    const sources = asArray(pick(caps, 'sources', 'ingestion.sources', 'evidence.sources'));
    const lastIngestionMap = asObject(pick(caps, 'lastIngestion', 'lastSuccessfulIngestion', 'ingestion.lastSuccessBySource'));
    const indexBuilds = asArray(pick(caps, 'indexBuilds', 'readyIndexBuilds', 'evidence.indexBuilds'));
    const manifests = asArray(pick(caps, 'manifests', 'readyManifests', 'datasets', 'evidenceSnapshots'));
    const coverage = asArray(pick(caps, 'missingCoverage', 'coverage.missing', 'coverageGaps'));
    const failedJobs = asArray(pick(caps, 'failedJobs', 'jobs.failed'));
    const usage = pick(caps, 'usage', 'usageAgainstBudget', 'budget');
    const deps = pick(caps, 'dependencies', 'readiness');

    return (
        <>
            <Panel title="Status" icon="fa-traffic-light" actions={<span className="fi-small">checked <Instant value={report.checkedAt} inline /></span>}>
                <div className="fi-health-status">
                    <Tag tone={statusTone(report.status)}>
                        <i className={`fas ${report.status === 'ready' ? 'fa-check-circle' : report.status === 'degraded' ? 'fa-exclamation-circle' : 'fa-times-circle'}`}></i> {report.status}
                    </Tag>
                </div>
                <h3 className="fi-h3">Dependency readiness</h3>
                <table className="fi-table fi-table-dense">
                    <thead><tr><th>Dependency</th><th>Ready</th><th>Details</th></tr></thead>
                    <tbody>
                        <tr><td>Application database</td><td><PassFail passed={report.database.ready} /></td>
                            <td className="fi-small">{report.database.error ?? `${report.database.queuedRuns} queued, ${report.database.runningRuns} running runs`}</td></tr>
                        <tr><td>Research engine reachable</td><td><PassFail passed={report.researchEngine.reachable} /></td>
                            <td className="fi-small">{report.researchEngine.error ?? DASH}</td></tr>
                        <tr><td>Research engine ready</td><td><PassFail passed={report.researchEngine.ready} /></td>
                            <td className="fi-small">schemas {report.researchEngine.schemaVersions.join(', ') || DASH}</td></tr>
                        <tr><td>Engine version allowed</td><td><PassFail passed={report.researchEngine.engineVersionAllowed} /></td>
                            <td className="fi-small">running {report.researchEngine.engineVersion ?? DASH}; allowed {report.allowedEngineVersions.join(', ') || 'any'}</td></tr>
                        <tr><td>Result signing key configured</td><td><PassFail passed={report.signingKeyConfigured} /></td><td className="fi-small">verifies engine results</td></tr>
                        <tr><td>Engine API key configured</td><td><PassFail passed={report.apiKeyConfigured} /></td><td className="fi-small">authenticates internal calls</td></tr>
                        {dependencyRows(deps)}
                    </tbody>
                </table>
            </Panel>

            <div className="fi-two-col">
                <Panel title="Last successful ingestion per source" icon="fa-download">
                    {sources.length === 0 && !lastIngestionMap ? <NotReported what="source freshness" /> : (
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Source</th><th>Status</th><th>Last success</th><th>Last attempt</th><th>Failures</th></tr></thead>
                            <tbody>
                                {sources.map((s, i) => {
                                    const status = pickStr(s, 'health.status', 'status') ?? 'unknown';
                                    return (
                                        <tr key={pickStr(s, 'sourceId') ?? i}>
                                            <td className="mono">{pickStr(s, 'sourceId', 'id')}<div className="fi-small">{pickStr(s, 'name')}</div></td>
                                            <td><Tag tone={status === 'healthy' ? 'ok' : status === 'outage' ? 'fail' : 'warn'}>{status}</Tag></td>
                                            <td><Instant value={pickStr(s, 'health.lastSuccessAt', 'lastSuccessAt', 'lastSuccessfulIngestionAt')} /></td>
                                            <td><Instant value={pickStr(s, 'health.lastAttemptAt', 'lastAttemptAt')} /></td>
                                            <td className="fi-small">{pickStr(s, 'health.consecutiveFailures', 'consecutiveFailures') ?? '0'}{pickStr(s, 'health.lastError', 'lastError') ? ` · ${pickStr(s, 'health.lastError', 'lastError')}` : ''}</td>
                                        </tr>
                                    );
                                })}
                                {lastIngestionMap && Object.entries(lastIngestionMap).map(([id, at]) => (
                                    <tr key={`m-${id}`}><td className="mono">{id}</td><td>{DASH}</td><td><Instant value={typeof at === 'string' ? at : pickStr(at, 'lastSuccessAt')} /></td><td>{DASH}</td><td>{DASH}</td></tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Panel>

                <Panel title="READY manifests and index builds" icon="fa-database">
                    {indexBuilds.length === 0 && manifests.length === 0 ? <NotReported what="index builds and manifests" /> : (
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Id</th><th>Kind</th><th>Status</th><th>Validated / created</th></tr></thead>
                            <tbody>
                                {indexBuilds.map((b, i) => (
                                    <tr key={`b-${i}`}>
                                        <td className="mono">{pickStr(b, 'buildId', 'indexBuildId', 'id')}</td>
                                        <td>index build</td>
                                        <td><Tag tone={pickStr(b, 'status') === 'READY' ? 'ok' : pickStr(b, 'status') === 'FAILED' ? 'fail' : 'muted'}>{pickStr(b, 'status') ?? DASH}</Tag>
                                            {pickStr(b, 'error') && <div className="fi-small fi-fail-text">{pickStr(b, 'error')}</div>}</td>
                                        <td><Instant value={pickStr(b, 'validatedAt', 'createdAt')} /></td>
                                    </tr>
                                ))}
                                {manifests.map((m, i) => (
                                    <tr key={`m-${i}`}>
                                        <td className="mono">{pickStr(m, 'manifestId', 'snapshotId', 'datasetId', 'id')}</td>
                                        <td>{pickStr(m, 'kind', 'type') ?? 'manifest'}</td>
                                        <td><Tag tone={pickStr(m, 'status') === 'READY' || pickBool(m, 'eligibleForBenchmark') ? 'ok' : 'muted'}>{pickStr(m, 'status') ?? (pickBool(m, 'eligibleForBenchmark') ? 'eligible' : DASH)}</Tag></td>
                                        <td><Instant value={pickStr(m, 'validatedAt', 'createdAt', 'generatedAt')} /></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Panel>
            </div>

            <div className="fi-two-col">
                <Panel title="Missing coverage" icon="fa-th">
                    {coverage.length === 0 ? <NotReported what="coverage gaps" emptyOk /> : (
                        <ul className="fi-list">
                            {coverage.map((c, i) => <li key={i}>{typeof c === 'string' ? c : JSON.stringify(c)}</li>)}
                        </ul>
                    )}
                </Panel>
                <Panel title="Usage against budget" icon="fa-coins">
                    {usage === undefined ? <NotReported what="usage against budget" /> : <UsageTable usage={usage} />}
                </Panel>
            </div>

            {failedJobs.length > 0 && (
                <Panel title="Failed engine jobs" icon="fa-times-circle">
                    <table className="fi-table fi-table-dense">
                        <thead><tr><th>Job</th><th>Kind</th><th>Failed at</th><th>Error</th></tr></thead>
                        <tbody>
                            {failedJobs.map((j, i) => (
                                <tr key={i}>
                                    <td className="mono">{pickStr(j, 'jobId', 'id')}</td>
                                    <td>{pickStr(j, 'kind', 'type')}</td>
                                    <td><Instant value={pickStr(j, 'failedAt', 'completedAt', 'updatedAt')} /></td>
                                    <td className="fi-small fi-fail-text">{pickStr(j, 'error', 'reason')}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Panel>
            )}
            <JsonDetails value={report.researchEngine.capabilities} summary="Raw engine capabilities" />
        </>
    );
}

function dependencyRows(deps: unknown) {
    const obj = asObject(deps);
    if (obj) {
        return Object.entries(obj).map(([name, value]) => {
            const ready = typeof value === 'boolean' ? value : pickBool(value, 'ready', 'ok');
            return (
                <tr key={`dep-${name}`}>
                    <td>{humanize(name)}</td>
                    <td><PassFail passed={ready ?? null} /></td>
                    <td className="fi-small">{typeof value === 'string' ? value : pickStr(value, 'status', 'detail', 'error') ?? DASH}</td>
                </tr>
            );
        });
    }
    return asArray(deps).map((d, i) => (
        <tr key={`dep-${i}`}>
            <td>{pickStr(d, 'name', 'id')}</td>
            <td><PassFail passed={pickBool(d, 'ready', 'ok') ?? null} /></td>
            <td className="fi-small">{pickStr(d, 'status', 'detail', 'error') ?? DASH}</td>
        </tr>
    ));
}

function UsageTable({ usage }: { usage: unknown }) {
    const rows = Array.isArray(usage)
        ? usage.map(u => ({ name: pickStr(u, 'name', 'resource', 'id') ?? DASH, used: pickStr(u, 'used', 'consumed'), limit: pickStr(u, 'limit', 'budget', 'max') }))
        : Object.entries(asObject(usage) ?? {}).map(([name, v]) => ({
            name,
            used: typeof v === 'object' && v !== null ? pickStr(v, 'used', 'consumed') : String(v),
            limit: typeof v === 'object' && v !== null ? pickStr(v, 'limit', 'budget', 'max') : undefined,
        }));
    if (rows.length === 0) return <p className="fi-muted-note">No usage recorded.</p>;
    return (
        <table className="fi-table fi-table-dense">
            <thead><tr><th>Resource</th><th>Used</th><th>Budget</th></tr></thead>
            <tbody>
                {rows.map(r => <tr key={r.name}><td>{humanize(r.name)}</td><td className="mono">{r.used ?? DASH}</td><td className="mono">{r.limit ?? 'no limit declared'}</td></tr>)}
            </tbody>
        </table>
    );
}

function NotReported({ what, emptyOk = false }: { what: string; emptyOk?: boolean }) {
    return (
        <p className="fi-muted-note">
            <i className="fas fa-info-circle"></i> {emptyOk ? `No ${what} reported.` : `The research engine capabilities do not report ${what} yet.`}
        </p>
    );
}

function FailedRunsPanel() {
    const query = useFailedRuns();
    return (
        <Panel title="Failed runs" icon="fa-exclamation-triangle">
            <QueryState query={query} label="failed runs" compact isEmpty={d => d.items.length === 0} emptyMessage="No failed runs.">
                {data => (
                    <table className="fi-table fi-table-dense">
                        <thead><tr><th>Run</th><th>State</th><th>Reason</th><th>Completed (operational)</th></tr></thead>
                        <tbody>
                            {data.items.map(r => (
                                <tr key={r.runId}>
                                    <td><Link to={`/fi/runs/${encodeURIComponent(r.runId)}`} className="mono">{r.runId}</Link><div className="fi-small">{r.experimentId}</div></td>
                                    <td><JobStateBadge state={r.jobState} /></td>
                                    <td className="fi-small fi-fail-text">{r.statusReason ?? 'no reason recorded'}</td>
                                    <td><Instant value={r.completedAt ?? r.startedAt ?? r.createdAt} /></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </QueryState>
        </Panel>
    );
}

function JobStatus({ result }: { result: unknown }) {
    const jobId = pickStr(result, 'jobId', 'job.jobId', 'id');
    const runId = pickStr(result, 'runId');
    const job = useAdminJob(jobId);
    return (
        <div className="fi-small">
            {runId && <div>Run <Link to={`/fi/runs/${encodeURIComponent(runId)}`} className="mono">{runId}</Link> ({pickStr(result, 'jobState') ?? 'queued'})</div>}
            {jobId && (
                <div>
                    Job <span className="mono">{jobId}</span>:{' '}
                    {job.isLoading ? 'checking…'
                        : job.isError ? <span className="fi-muted">status endpoint unavailable</span>
                            : <Tag tone="muted">{pickStr(job.data, 'state', 'status') ?? 'unknown'}</Tag>}
                </div>
            )}
            <JsonDetails value={result} summary="Response" />
        </div>
    );
}

function OperatorPanel() {
    const [token, setToken] = useState(() => getAccessToken() ?? '');
    const [savedToken, setSavedToken] = useState(() => !!getAccessToken());
    const [sources, setSources] = useState('');
    const [reason, setReason] = useState('');
    const [snapshot, setSnapshot] = useState('');
    const [baseBuild, setBaseBuild] = useState('');
    const [validateOnly, setValidateOnly] = useState(false);
    const [experimentId, setExperimentId] = useState('');
    const [responseMode, setResponseMode] = useState<ResponseMode>('recorded_replay');

    return (
        <Panel title="Operator actions" icon="fa-user-cog">
            <Notice icon="fa-lock">
                These buttons call the admin endpoints. The server requires the Operator role; read-only viewers receive 401/403,
                which is shown next to the button. Long operations return job ids instead of holding the connection open.
            </Notice>
            <div className="fi-filters">
                <label>Session access token (kept in this browser tab only)
                    <input type="password" value={token} autoComplete="off" onChange={e => setToken(e.target.value)} placeholder="Bearer token" />
                </label>
                <button className="fi-button" onClick={() => { setAccessToken(token.trim() || null); setSavedToken(!!token.trim()); }}>
                    <i className="fas fa-key"></i> {token.trim() ? 'Use token' : 'Clear token'}
                </button>
                <span className="fi-small">{savedToken ? 'A token is attached to /api/v1 requests.' : 'No token: requests are anonymous.'}</span>
            </div>

            <div className="fi-operator-grid">
                <div>
                    <h3 className="fi-h3">Trigger ingestion</h3>
                    <div className="fi-filters">
                        <label>Source ids (comma separated, empty = all)
                            <input type="text" value={sources} onChange={e => setSources(e.target.value)} placeholder="fed-fomc" />
                        </label>
                        <label>Reason
                            <input type="text" value={reason} onChange={e => setReason(e.target.value)} />
                        </label>
                    </div>
                    <OperatorAction
                        label="Start ingestion"
                        icon="fa-download"
                        action={() => fiApi.startIngestion({
                            sourceIds: sources.split(',').map(s => s.trim()).filter(Boolean),
                            reason: reason || undefined,
                        })}
                        renderResult={r => <JobStatus result={r} />}
                    />
                </div>
                <div>
                    <h3 className="fi-h3">Build or validate an index</h3>
                    <div className="fi-filters">
                        <label>Evidence snapshot
                            <input type="text" value={snapshot} onChange={e => setSnapshot(e.target.value)} placeholder="latest" />
                        </label>
                        <label>Base index build
                            <input type="text" value={baseBuild} onChange={e => setBaseBuild(e.target.value)} placeholder="none" />
                        </label>
                        <label className="fi-checkbox">
                            <input type="checkbox" checked={validateOnly} onChange={e => setValidateOnly(e.target.checked)} /> Validate only
                        </label>
                    </div>
                    <OperatorAction
                        label={validateOnly ? 'Validate index' : 'Start index build'}
                        icon="fa-database"
                        action={() => fiApi.startIndexBuild({
                            evidenceSnapshotId: snapshot || undefined,
                            baseIndexBuildId: baseBuild || undefined,
                            validateOnly,
                            reason: reason || undefined,
                        })}
                        renderResult={r => <JobStatus result={r} />}
                    />
                    <p className="fi-small">Builds never mutate an existing READY manifest.</p>
                </div>
                <div>
                    <h3 className="fi-h3">Trigger a forward paper cycle</h3>
                    <div className="fi-filters">
                        <label>Experiment id
                            <input type="text" value={experimentId} onChange={e => setExperimentId(e.target.value)} />
                        </label>
                        <label>Responses
                            <select value={responseMode} onChange={e => setResponseMode(e.target.value as ResponseMode)}>
                                <option value="recorded_replay">Recorded replay</option>
                                <option value="fresh_inference">Fresh inference</option>
                            </select>
                        </label>
                    </div>
                    <OperatorAction
                        label="Trigger paper cycle"
                        icon="fa-play"
                        disabled={!experimentId.trim()}
                        action={() => fiApi.triggerPaperCycle({ experimentId: experimentId.trim(), responseMode })}
                        renderResult={r => <JobStatus result={r as JsonObject} />}
                    />
                </div>
            </div>
        </Panel>
    );
}
