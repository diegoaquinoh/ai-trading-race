import { useParams } from 'react-router-dom';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useCurve } from '../api/hooks';
import type { CurveSnapshot } from '../api/types';
import { DataModeBadge, PassFail, Tag, ValueKindTag } from '../components/Badges';
import { Instant, SessionDate } from '../components/Instant';
import { IdList, JsonDetails, KeyValueGrid, Notice, PageHeader, Panel, StringList } from '../components/Layout';
import { QueryState } from '../components/States';
import { DASH, fmtNumber, fmtPct, fmtPrice, humanize, shortHash } from '../lib/format';

export function CurveView() {
    const { snapshotId } = useParams();
    const query = useCurve(snapshotId);
    return (
        <div className="fi-page">
            <QueryState query={query} label="curve snapshot" notFoundMessage={`Curve snapshot '${snapshotId}' was not found.`}>
                {curve => <CurveBody curve={curve} />}
            </QueryState>
        </div>
    );
}

function CurveBody({ curve }: { curve: CurveSnapshot }) {
    const spec = curve.specification;
    const nodes = curve.nodes ?? [];
    const chartData = nodes.map(n => ({ t: Number(n.timeYears), zero: Number(n.zeroRate), date: n.nodeDate, tenor: n.sourceTenor ?? 'reference' }));
    const ready = curve.status === 'READY';

    return (
        <>
            <PageHeader
                icon="fa-chart-line"
                title={<span className="mono">{curve.curveSnapshotId}</span>}
                breadcrumbs={[{ to: '/fi', label: 'Research lab' }]}
                subtitle={`${curve.curveId} · spec ${curve.version} · session ${curve.sessionDate}`}
            >
                {curve.dataMode && <DataModeBadge mode={curve.dataMode} />}
                <Tag tone={ready ? 'ok' : 'fail'}>{curve.status}</Tag>
            </PageHeader>
            {!ready && (
                <Notice tone="fail">
                    Curve build failed. Decisions and valuations that require it are skipped or marked incomplete.
                    <StringList items={curve.failureReasons} />
                </Notice>
            )}

            <Panel title="Snapshot" icon="fa-info-circle">
                <KeyValueGrid
                    columns={4}
                    items={[
                        { label: 'Session date', value: <SessionDate value={curve.sessionDate} /> },
                        { label: 'Reference date', value: <SessionDate value={curve.referenceDate} label="reference date (D = 1)" /> },
                        { label: 'Observation instant', value: <Instant value={curve.valuationAt} context="market" /> },
                        { label: 'Available at', value: <Instant value={curve.availableAt} context="market" /> },
                        { label: 'Validated horizon', value: <SessionDate value={curve.validatedHorizonDate} label="last node" /> },
                        { label: 'Engine version', value: curve.engineVersion },
                        { label: 'Content hash', value: <span className="mono">{shortHash(curve.contentHash)}</span> },
                        { label: 'Currency', value: curve.currency ?? 'USD' },
                    ]}
                />
            </Panel>

            <Panel title="Inputs" icon="fa-sign-in-alt">
                <p className="fi-small">Published par yields (indicative, bid-side, never execution quotes). Missing tenors are excluded, never filled.</p>
                <KeyValueGrid
                    columns={2}
                    items={[
                        { label: 'Input observations', value: <IdList ids={curve.inputObservationIds} /> },
                        { label: 'Observation hashes', value: <IdList ids={(curve.inputObservationHashes ?? []).map(h => shortHash(h))} /> },
                        { label: 'Used tenors', value: (curve.usedTenors ?? []).join(', ') || DASH },
                        { label: 'Excluded tenors', value: (curve.excludedTenors ?? []).join(', ') || 'none' },
                    ]}
                />
            </Panel>

            <Panel title="Specification" icon="fa-cogs">
                <KeyValueGrid
                    columns={3}
                    items={[
                        { label: 'Spec', value: <span className="mono">{spec.specId} ({spec.version})</span> },
                        { label: 'Family', value: humanize(spec.curveFamily) },
                        { label: 'Input source', value: <span className="mono">{spec.inputSourceId}</span> },
                        { label: 'Calendar', value: `${spec.calendarId ?? DASH} (${spec.calendarVersion ?? DASH})` },
                        { label: 'Time day count', value: spec.timeDayCount },
                        { label: 'Zero-rate convention', value: humanize(spec.zeroRateConvention) },
                        { label: 'Interpolation', value: humanize(spec.interpolation) },
                        { label: 'Extrapolation', value: humanize(spec.extrapolation) },
                        { label: 'Engine', value: spec.engine },
                        { label: 'Short end', value: spec.shortEndTreatment?.description },
                        { label: 'Required tenors', value: (spec.requiredTenors ?? []).join(', ') },
                        { label: 'Minimum nodes', value: spec.minNodes },
                    ]}
                />
                {(spec.instruments ?? []).length > 0 && (
                    <div className="fi-table-wrap">
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Tenor</th><th>Calibration instrument</th><th>Quote convention</th><th>Day count</th><th>Coupon freq.</th></tr></thead>
                            <tbody>
                                {(spec.instruments ?? []).map(i => (
                                    <tr key={i.tenor}><td className="mono">{i.tenor}</td><td>{humanize(i.kind)}</td><td className="fi-small">{humanize(i.quoteConvention)}</td><td>{i.dayCount}</td><td>{i.couponFrequency ?? DASH}</td></tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
                <JsonDetails value={spec.tolerances} summary="Solver tolerances" />
            </Panel>

            <div className="fi-two-col">
                <Panel title="Zero curve nodes" icon="fa-chart-area">
                    <p className="fi-small"><ValueKindTag kind="model" /> Fitted continuous ACT/365F zero rates by node time.</p>
                    {chartData.length < 2 ? <p className="fi-muted-note">No nodes to chart.</p> : (
                        <div className="fi-chart">
                            <ResponsiveContainer width="100%" height={260}>
                                <LineChart data={chartData} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
                                    <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                                    <XAxis dataKey="t" type="number" domain={[0, 'dataMax']} stroke="var(--text-secondary)" fontSize={11} tickLine={false}
                                        tickFormatter={(t: number) => `${t.toFixed(1)}y`} />
                                    <YAxis stroke="var(--text-secondary)" fontSize={11} tickLine={false} width={64} domain={['auto', 'auto']}
                                        tickFormatter={(v: number) => fmtPct(v, 2)} />
                                    <Tooltip
                                        contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-light)', borderRadius: 8 }}
                                        labelStyle={{ color: 'var(--text-secondary)' }}
                                        itemStyle={{ color: 'var(--text-primary)' }}
                                        labelFormatter={t => `t = ${Number(t).toFixed(4)} y`}
                                        formatter={value => [fmtPct(Number(value), 4), 'Zero rate']}
                                    />
                                    <Line type="linear" dataKey="zero" stroke="#3987e5" strokeWidth={2} dot={{ r: 4, stroke: 'var(--bg-card)', strokeWidth: 2, fill: '#3987e5' }} isAnimationActive={false} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    )}
                    <div className="fi-table-wrap">
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Node date</th><th>Tenor</th><th>Time (y)</th><th>Discount factor</th><th>Zero rate</th></tr></thead>
                            <tbody>
                                {nodes.map(n => (
                                    <tr key={n.nodeDate}><td className="mono">{n.nodeDate}</td><td>{n.sourceTenor ?? 'reference'}</td><td className="mono">{fmtNumber(n.timeYears, 4)}</td><td className="mono">{fmtNumber(n.discountFactor, 8)}</td><td className="mono">{fmtPct(n.zeroRate, 4)}</td></tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </Panel>

                <Panel title="Calibration residuals" icon="fa-crosshairs">
                    <KeyValueGrid
                        columns={2}
                        items={[
                            { label: 'Max |price residual|', value: curve.maxAbsPriceResidualPer100 ? `${fmtPrice(curve.maxAbsPriceResidualPer100, 8)} per 100` : undefined },
                            { label: 'Max |rate residual|', value: curve.maxAbsRateResidual ? fmtPct(curve.maxAbsRateResidual, 6) : undefined },
                        ]}
                    />
                    {(curve.residuals ?? []).length === 0 ? <p className="fi-muted-note">No residuals reported.</p> : (
                        <div className="fi-table-wrap">
                            <table className="fi-table fi-table-dense">
                                <thead><tr><th>Tenor</th><th>Kind</th><th>Input</th><th>Model</th><th>Rate residual</th><th>Price residual</th><th>Tolerance</th></tr></thead>
                                <tbody>
                                    {(curve.residuals ?? []).map(r => (
                                        <tr key={r.tenor}>
                                            <td className="mono">{r.tenor}</td>
                                            <td className="fi-small">{humanize(r.kind)}</td>
                                            <td className="mono">{fmtPct(r.inputQuote, 4)}</td>
                                            <td className="mono">{fmtPct(r.modelQuote, 4)}</td>
                                            <td className="mono">{r.rateResidual}</td>
                                            <td className="mono">{r.priceResidualPer100 ?? r.pricePer100Residual ?? DASH}</td>
                                            <td><PassFail passed={r.withinTolerance} label={r.withinTolerance ? 'within' : 'outside'} /></td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </Panel>
            </div>
            <JsonDetails value={curve} summary="Raw curve snapshot" />
        </>
    );
}
