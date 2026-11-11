import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useInstrumentValuation, useInstruments } from '../api/hooks';
import type { SecurityTerms } from '../api/types';
import { SyntheticBadge, Tag, ValueKindTag } from '../components/Badges';
import { Instant, SessionDate } from '../components/Instant';
import { IdList, JsonDetails, KeyValueGrid, Notice, PageHeader, Panel, StringList } from '../components/Layout';
import { QueryState } from '../components/States';
import { DASH, fmtNumber, fmtPct, fmtPrice, fmtUsd, humanize } from '../lib/format';
import { isSyntheticTerms, readInstrumentValuation, relativeValueAvailable } from '../lib/instrument';
import type { InstrumentValuationView } from '../lib/instrument';

export function InstrumentDetail() {
    const { securityId } = useParams();
    const [date, setDate] = useState('');
    const termsQuery = useInstruments({ securityId, pageSize: 5 });
    const valuationQuery = useInstrumentValuation(securityId, date);
    const valuation = valuationQuery.data ? readInstrumentValuation(valuationQuery.data) : undefined;
    const terms: SecurityTerms | undefined = termsQuery.data?.items.find(t => t.identity.securityId === securityId)
        ?? termsQuery.data?.items[0]
        ?? valuation?.terms;
    const synthetic = isSyntheticTerms(terms, securityId) || valuation?.synthetic === true || valuation?.dataMode === 'synthetic_curve';

    return (
        <div className="fi-page">
            {synthetic && (
                <div className="fi-synthetic-banner" role="note">
                    <SyntheticBadge large />
                    <span>Hypothetical instrument with an internal identifier. It does not represent an actual security, and every
                        price on this page is a curve-model value, not a market quote.</span>
                </div>
            )}
            <PageHeader
                icon="fa-file-contract"
                title={<><span className="mono">{securityId}</span> {synthetic && <SyntheticBadge />}</>}
                breadcrumbs={[{ to: '/fi', label: 'Research lab' }, { to: '/fi/instruments', label: 'Instruments' }]}
                subtitle={terms?.identity.displayName}
            >
                <label className="fi-inline-label">Valuation date (session, date only)
                    <input type="date" value={date} onChange={e => setDate(e.target.value)} />
                </label>
            </PageHeader>

            <Panel title="Contractual terms and provenance" icon="fa-file-signature">
                {terms ? <TermsView terms={terms} /> : (
                    <QueryState query={termsQuery} label="terms" isEmpty={() => true} emptyMessage="No admitted term version found for this security.">
                        {() => null}
                    </QueryState>
                )}
            </Panel>

            <QueryState
                query={valuationQuery}
                label="valuation"
                notFoundMessage="The instrument valuation endpoint is not available yet (404), or no valuation exists for this date."
            >
                {() => valuation ? <ValuationView v={valuation} synthetic={synthetic} raw={valuationQuery.data} /> : null}
            </QueryState>
        </div>
    );
}

function TermsView({ terms }: { terms: SecurityTerms }) {
    const ext = terms.identity.externalIdentifiers ?? [];
    return (
        <>
            <KeyValueGrid
                columns={4}
                items={[
                    { label: 'Classification', value: isSyntheticTerms(terms) ? <SyntheticBadge /> : <Tag tone="ok">actual</Tag> },
                    { label: 'Issuer', value: <span className="mono">{terms.identity.issuerId}</span> },
                    { label: 'External identifiers', value: ext.length ? ext.map(e => `${e.scheme} ${e.value}`).join(', ') : 'none (never fabricated)' },
                    { label: 'Instrument type', value: humanize(terms.economics.instrumentType ?? 'fixed_rate_note') },
                    { label: 'Coupon rate', value: <span className="mono">{fmtPct(terms.economics.couponRate, 3)}</span>, hint: 'Decimal annual rate' },
                    { label: 'Coupon frequency', value: terms.economics.couponFrequency === 2 ? 'Semiannual' : terms.economics.couponFrequency },
                    { label: 'Redemption', value: <span className="mono">{fmtPrice(terms.economics.redemptionPer100 ?? '100', 2)} per 100</span> },
                    { label: 'Currency', value: terms.economics.currency ?? 'USD' },
                    { label: 'Original issue', value: <SessionDate value={terms.dates.originalIssueDate} label="contract date" /> },
                    { label: 'Dated date', value: <SessionDate value={terms.dates.datedDate} label="contract date" /> },
                    { label: 'First coupon', value: terms.dates.firstCouponDate ? <SessionDate value={terms.dates.firstCouponDate} label="contract date" /> : 'regular schedule' },
                    { label: 'Maturity', value: <SessionDate value={terms.dates.maturityDate} label="contract date" /> },
                    { label: 'Day count', value: terms.conventions?.dayCount },
                    { label: 'Business day', value: terms.conventions?.businessDayAdjustment },
                    { label: 'Calendar', value: `${terms.conventions?.calendarId ?? DASH} (${terms.conventions?.calendarVersion ?? DASH})` },
                    { label: 'Settlement lag', value: terms.conventions?.settlementLagBusinessDays !== undefined ? `T+${terms.conventions.settlementLagBusinessDays}` : undefined },
                    { label: 'Quote basis', value: humanize(terms.conventions?.priceQuoteBasis) },
                    { label: 'Yield convention', value: humanize(terms.conventions?.yieldConvention) },
                    { label: 'Minimum / increment face', value: `${fmtNumber(terms.tradingUnits?.minFaceUsd, 0)} / ${fmtNumber(terms.tradingUnits?.faceIncrementUsd, 0)}` },
                    { label: 'Terms version', value: <span className="mono">{terms.termsVersion}</span> },
                    { label: 'Effective', value: `${terms.termsEffectiveFrom}${terms.termsEffectiveTo ? ` → ${terms.termsEffectiveTo}` : ' → open'}` },
                ]}
            />
            <h3 className="fi-h3">Provenance</h3>
            <KeyValueGrid
                columns={3}
                items={[
                    { label: 'Source', value: <span className="mono">{terms.provenance.sourceId}</span> },
                    { label: 'Artifact', value: <span className="mono fi-break">{terms.provenance.sourceArtifact}{terms.provenance.sourceRow ? ` #${terms.provenance.sourceRow}` : ''}</span> },
                    { label: 'Checksum', value: <span className="mono fi-break">{terms.provenance.checksum ?? DASH}</span> },
                    { label: 'Validation status', value: <Tag tone={terms.provenance.validationStatus === 'validated' ? 'ok' : 'muted'}>{terms.provenance.validationStatus}</Tag> },
                    { label: 'Available from (policy)', value: <Instant value={terms.provenance.availableAt} context="market" /> },
                    { label: 'Notes', value: terms.provenance.notes },
                ]}
            />
        </>
    );
}

function ValuationView({ v, synthetic, raw }: { v: InstrumentValuationView; synthetic: boolean; raw: unknown }) {
    const rvAvailable = relativeValueAvailable(v.relativeValue);
    return (
        <>
            <Panel title="Valuation" icon="fa-calculator">
                <KeyValueGrid
                    columns={4}
                    items={[
                        { label: 'Valuation date', value: <SessionDate value={v.valuationDate} label="valuation date" /> },
                        { label: 'Settlement date', value: <SessionDate value={v.settlementDate} label="settlement date" /> },
                        { label: 'Curve snapshot', value: v.curveSnapshotId ? <Link to={`/fi/curves/${encodeURIComponent(v.curveSnapshotId)}`} className="mono">{v.curveSnapshotId}</Link> : undefined },
                        { label: 'Curve specification', value: <span className="mono">{v.curveSpecId ?? DASH}</span> },
                        { label: 'Calibration max |price residual|', value: v.curveMaxAbsPriceResidual ? `${fmtPrice(v.curveMaxAbsPriceResidual, 6)} per 100` : undefined },
                        { label: 'Face basis', value: v.faceUsd ? `${fmtNumber(v.faceUsd, 0)} USD face` : 'per 100 face' },
                        { label: 'Engine', value: v.engineVersion },
                        { label: 'Calculation ids', value: <IdList ids={v.calculationIds} /> },
                    ]}
                />
                <div className="fi-value-cards">
                    <div className="fi-value-card fi-value-card-model">
                        <div className="fi-value-card-head">
                            <ValueKindTag kind="model" />
                            <span className="fi-small">Discounted under the named curve and convention set</span>
                        </div>
                        <dl className="fi-value-list">
                            <div><dt>Clean price</dt><dd className="mono">{fmtPrice(v.model.cleanPricePer100)} <small>per 100</small></dd></div>
                            <div><dt>Accrued interest</dt><dd className="mono">{fmtPrice(v.model.accruedPer100, 6)} <small>per 100</small></dd></div>
                            <div><dt>Dirty price</dt><dd className="mono">{fmtPrice(v.model.dirtyPricePer100)} <small>per 100</small></dd></div>
                            {v.model.accruedInterestUsd && <div><dt>Accrued (face-scaled)</dt><dd className="mono">{fmtUsd(v.model.accruedInterestUsd)}</dd></div>}
                            <div><dt>Yield to maturity</dt><dd className="mono">{fmtPct(v.model.ytm ?? v.risk.ytm, 4)}</dd></div>
                        </dl>
                        {v.model.calculationId && <div className="fi-small">calculation <code className="fi-code">{v.model.calculationId}</code></div>}
                    </div>
                    <div className="fi-value-card fi-value-card-quote">
                        <div className="fi-value-card-head">
                            <ValueKindTag kind="quote" />
                        </div>
                        {v.observed ? (
                            <dl className="fi-value-list">
                                <div><dt>Quote type</dt><dd>{humanize(v.observed.kind)} {v.observed.executable === false && <Tag tone="muted">indicative</Tag>}</dd></div>
                                <div><dt>Bid / ask</dt><dd className="mono">{fmtPrice(v.observed.bidPer100)} / {fmtPrice(v.observed.askPer100)}</dd></div>
                                <div><dt>Mid</dt><dd className="mono">{fmtPrice(v.observed.midPer100)}</dd></div>
                                <div><dt>Basis</dt><dd>{v.observed.priceBasis ?? DASH}</dd></div>
                                <div><dt>Observed at</dt><dd><Instant value={v.observed.observedAt} context="market" /></dd></div>
                                <div><dt>Available at</dt><dd><Instant value={v.observed.availableAt} context="market" /></dd></div>
                            </dl>
                        ) : (
                            <p className="fi-muted-note">
                                {synthetic
                                    ? 'No observed quote: synthetic instruments have no market. Execution and marks use curve-model observations.'
                                    : 'No admitted observed quote for this date; the valuation state is stale or incomplete under policy.'}
                            </p>
                        )}
                    </div>
                </div>
                {v.diagnostics.length > 0 && (<><h3 className="fi-h3">Diagnostics</h3><StringList items={v.diagnostics} /></>)}
            </Panel>

            <div className="fi-two-col">
                <Panel title="Upcoming payments" icon="fa-calendar-alt">
                    {v.cashFlows.length === 0 ? <p className="fi-muted-note">No upcoming payments reported.</p> : (
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Payment date</th><th>Kind</th><th>Amount per 100</th><th>Amount (USD)</th><th>Accrual period</th></tr></thead>
                            <tbody>
                                {v.cashFlows.map((cf, i) => (
                                    <tr key={`${cf.paymentDate}-${cf.kind}-${i}`}>
                                        <td><SessionDate value={cf.paymentDate} label="payment date" /></td>
                                        <td>{humanize(cf.kind)}</td>
                                        <td className="mono">{fmtPrice(cf.amountPer100, 6)}</td>
                                        <td className="mono">{fmtUsd(cf.amountUsd)}</td>
                                        <td className="fi-small mono">{cf.accrualStart ? `${cf.accrualStart} → ${cf.accrualEnd}` : DASH}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Panel>

                <Panel title="Risk" icon="fa-tachometer-alt">
                    <p className="fi-small"><ValueKindTag kind="model" /> Curve-based sensitivities from the valuation engine.</p>
                    <KeyValueGrid
                        columns={2}
                        items={[
                            { label: 'Effective duration', value: v.risk.effectiveDurationYears ? `${fmtNumber(v.risk.effectiveDurationYears, 3)} y` : undefined, hint: 'Curve-based (parallel zero shift)' },
                            { label: 'Yield modified duration', value: v.risk.yieldModifiedDurationYears ? `${fmtNumber(v.risk.yieldModifiedDurationYears, 3)} y` : undefined },
                            { label: 'Effective convexity', value: fmtNumber(v.risk.effectiveConvexity, 3) },
                            { label: 'Parallel DV01', value: v.risk.parallelDv01 ? `${fmtNumber(v.risk.parallelDv01, 4)}${v.risk.dv01Basis ? ` (${v.risk.dv01Basis})` : ''}` : undefined },
                            { label: 'Remaining maturity', value: v.risk.remainingMaturityYears ? `${fmtNumber(v.risk.remainingMaturityYears, 2)} y` : undefined },
                            { label: 'Maturity bucket', value: v.risk.maturityBucket },
                        ]}
                    />
                    <h3 className="fi-h3">Key-rate DV01</h3>
                    {v.risk.keyRates.length === 0 ? <p className="fi-muted-note">Not reported.</p> : (
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Key tenor (y)</th><th>DV01</th></tr></thead>
                            <tbody>
                                {v.risk.keyRates.map((k, i) => (
                                    <tr key={`${k.keyTenorYears}-${i}`}><td className="mono">{k.keyTenorYears}</td><td className="mono">{fmtNumber(k.dv01, 4)}</td></tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                    {v.risk.keyRateSumMinusParallel && <p className="fi-small">Key-rate sum minus parallel: <span className="mono">{v.risk.keyRateSumMinusParallel}</span></p>}
                </Panel>
            </div>

            <div className="fi-two-col">
                <Panel title="Scenario prices" icon="fa-random">
                    <p className="fi-small"><ValueKindTag kind="model" /> Hypothetical instantaneous curve shifts with holdings fixed; not forecasts.</p>
                    {v.scenarios.length === 0 ? <p className="fi-muted-note">No scenarios reported.</p> : (
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Scenario</th><th>Shift (bp)</th><th>Clean price per 100</th><th>PV (USD)</th><th>P&amp;L</th></tr></thead>
                            <tbody>
                                {v.scenarios.map((s, i) => (
                                    <tr key={`${s.scenarioId}-${i}`}>
                                        <td>{s.scenarioId}<div className="fi-small">{s.description}</div></td>
                                        <td className="mono">{s.shiftBp ?? DASH}</td>
                                        <td className="mono">{fmtPrice(s.pricePer100)}</td>
                                        <td className="mono">{fmtUsd(s.pvUsd)}</td>
                                        <td className="mono">{fmtNumber(s.pnlUsd, 2)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Panel>

                <Panel title="Relative value" icon="fa-not-equal">
                    {rvAvailable ? (
                        <>
                            <p className="fi-small">Difference from an explicitly defined reference model; not guaranteed profit.</p>
                            <KeyValueGrid
                                columns={2}
                                items={[
                                    { label: 'Reference model', value: v.relativeValue?.referenceModel },
                                    { label: 'Clean price residual', value: v.relativeValue?.cleanPriceResidualPer100 ? `${fmtPrice(v.relativeValue.cleanPriceResidualPer100, 4)} per 100` : undefined },
                                    { label: 'Yield residual', value: fmtPct(v.relativeValue?.yieldResidual, 4) },
                                    { label: 'Notes', value: v.relativeValue?.reason },
                                ]}
                            />
                        </>
                    ) : (
                        <div className="fi-rv-unavailable">
                            <Tag tone="muted"><i className="fas fa-equals"></i> {v.relativeValue?.status === 'mechanically_neutral' ? 'Mechanically neutral' : 'Unavailable'}</Tag>
                            <p>
                                {v.relativeValue?.reason
                                    ?? (synthetic
                                        ? 'Synthetic same-curve mode: execution marks and the valuation benchmark use the same curve and model, so any rich/cheap difference is identically zero and is not a relative-value signal.'
                                        : 'No relative-value benchmark is available for this instrument.')}
                            </p>
                            {v.relativeValue?.status && <p className="fi-small mono">status: {v.relativeValue.status}</p>}
                        </div>
                    )}
                </Panel>
            </div>
            <JsonDetails value={raw} summary="Raw valuation response" />
            {synthetic && <Notice tone="warn" icon="fa-flask">All values above derive from hypothetical terms and the declared curve model.</Notice>}
        </>
    );
}
