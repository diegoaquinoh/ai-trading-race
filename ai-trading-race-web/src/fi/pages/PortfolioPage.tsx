import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useJournal, useOrders, usePortfolio, useValuations } from '../api/hooks';
import type { Portfolio, Valuation } from '../api/types';
import { DataModeBadge, PassFail, Tag, ValueKindTag } from '../components/Badges';
import { EquityCurves } from '../components/EquityCurves';
import { Instant, SessionDate, TimeLegend } from '../components/Instant';
import { IdList, KeyValueGrid, Notice, PageHeader, Panel, StringList } from '../components/Layout';
import { OrdersTable } from '../components/OrdersTable';
import { Pagination } from '../components/Pagination';
import { QueryState } from '../components/States';
import { ORDER_STATUSES } from '../lib/domain';
import { DASH, fmtFace, fmtNumber, fmtPrice, fmtUsd, humanize, shortHash } from '../lib/format';

export function PortfolioPage() {
    const { portfolioId } = useParams();
    const query = usePortfolio(portfolioId);
    return (
        <div className="fi-page">
            <QueryState query={query} label="portfolio" notFoundMessage={`Portfolio '${portfolioId}' was not found.`}>
                {p => <PortfolioBody portfolio={p} />}
            </QueryState>
        </div>
    );
}

function PortfolioBody({ portfolio: p }: { portfolio: Portfolio }) {
    const state = p.state ?? {};
    const latest = p.latestValuation;
    const positions = state.positions ?? [];
    return (
        <>
            <PageHeader
                icon="fa-briefcase"
                title={<span className="mono">{p.portfolioId}</span>}
                breadcrumbs={[{ to: '/fi', label: 'Experiments' }, { to: `/fi/runs/${encodeURIComponent(p.runId)}`, label: p.runId }]}
                subtitle={<>{p.strategyId} · repetition {p.repetition} · risk policy {p.riskPolicyId}</>}
            >
                <DataModeBadge mode={p.dataMode} label={p.dataModeLabel} />
                <Tag tone="muted" title={`State hash ${p.stateHash}`}>version {p.version}</Tag>
            </PageHeader>
            <TimeLegend />
            {p.blockedReason && (
                <Notice tone="fail" icon="fa-lock">
                    Portfolio blocked{p.blockedAt ? <> since <Instant value={p.blockedAt} inline /></> : null}: {p.blockedReason}. New
                    commitments are refused until an operator investigates.
                </Notice>
            )}

            <Panel title="Reconciled NAV" icon="fa-balance-scale">
                {!latest ? <p className="fi-muted-note">No valuation has been saved yet.</p> : (
                    <>
                        <div className="fi-nav-head">
                            <div>
                                <div className="fi-nav-value mono">{fmtUsd(latest.equityUsd)}</div>
                                <div className="fi-small">equity at <Instant value={latest.valuationAt} context="market" inline /></div>
                            </div>
                            <div>
                                {latest.complete
                                    ? <Tag tone="ok"><i className="fas fa-check"></i> complete</Tag>
                                    : <Tag tone="warn"><i className="fas fa-exclamation-triangle"></i> incomplete</Tag>}
                                <Tag tone="muted" title="Immutable experiment marking policy">{latest.markPolicy}</Tag>
                                {p.dataMode === 'synthetic_curve' && <ValueKindTag kind="model" />}
                            </div>
                        </div>
                        {!latest.complete && <StringList items={latest.incompleteReasons} empty="Incomplete without a stated reason." />}
                        <KeyValueGrid
                            columns={4}
                            items={[
                                { label: 'Settled cash', value: <span className="mono">{fmtUsd(latest.cashUsd)}</span> },
                                { label: 'Bond value', value: <span className="mono">{fmtUsd(latest.bondValueUsd)}</span> },
                                { label: 'Receivables PV', value: <span className="mono">{fmtUsd(latest.receivablesPvUsd)}</span> },
                                { label: 'Payables PV', value: <span className="mono">{fmtUsd(latest.payablesPvUsd)}</span> },
                                { label: 'Parallel DV01 (USD/bp)', value: <span className="mono">{fmtUsd(latest.parallelDv01Usd)}</span> },
                                { label: 'Effective duration', value: latest.effectiveDurationYears ? `${fmtNumber(latest.effectiveDurationYears, 3)} y` : DASH },
                                { label: 'Curve', value: latest.curveSnapshotId ? <Link to={`/fi/curves/${encodeURIComponent(latest.curveSnapshotId)}`} className="mono">{latest.curveSnapshotId}</Link> : DASH },
                                { label: 'State version valued', value: latest.stateVersion },
                            ]}
                        />
                    </>
                )}
            </Panel>

            <div className="fi-two-col">
                <Panel title="Cash" icon="fa-money-bill-wave">
                    <KeyValueGrid
                        columns={2}
                        items={[
                            { label: 'Settled cash', value: <span className="mono">{fmtUsd(p.cash?.settledCashUsd ?? state.cashUsd)}</span> },
                            { label: 'Available', value: <span className="mono" title={p.cash?.basis}>{p.cash ? fmtUsd(p.cash.availableCashUsd) : DASH}</span> },
                            { label: 'Committed (reserved + pending payables)', value: <span className="mono">{p.cash ? fmtUsd(p.cash.committedCashUsd) : DASH}</span> },
                            { label: 'Reserved for open purchase orders', value: <span className="mono">{fmtUsd(p.cash?.reservedCashUsd ?? state.reservedCashUsd)}</span> },
                            { label: 'Pending settlement payables', value: <span className="mono">{p.cash ? fmtUsd(p.cash.pendingPayablesUsd) : DASH}</span> },
                            { label: 'Pending settlement receivables', value: <span className="mono" title="Not available until settlement">{p.cash ? fmtUsd(p.cash.pendingReceivablesUsd) : DASH}</span> },
                            { label: 'External capital', value: <span className="mono">{fmtUsd(state.externalCapitalUsd)}</span> },
                            { label: 'Interest income', value: <span className="mono">{fmtUsd(state.interestIncomeUsd)}</span> },
                            { label: 'Realized gain/loss', value: <span className="mono">{fmtUsd(state.realizedGainLossUsd)}</span> },
                            { label: 'Transaction fees', value: <span className="mono">{fmtUsd(state.transactionFeesUsd)}</span> },
                            { label: 'Spread cost', value: <span className="mono">{fmtUsd(state.spreadCostUsd)}</span> },
                        ]}
                    />
                </Panel>
                <Panel title="Risk" icon="fa-shield-alt">
                    <KeyValueGrid
                        columns={2}
                        items={[
                            { label: 'Parallel DV01 (USD/bp)', value: <span className="mono">{fmtUsd(latest?.parallelDv01Usd)}</span> },
                            { label: 'Effective duration', value: latest?.effectiveDurationYears ? `${fmtNumber(latest.effectiveDurationYears, 3)} y` : DASH },
                            { label: 'Open orders', value: p.openOrderCount },
                            { label: 'Pending settlements', value: p.pendingSettlementCount },
                            { label: 'Cash flows processed through', value: <SessionDate value={state.cashFlowsProcessedThrough} /> },
                            { label: 'State hash', value: <span className="mono">{shortHash(p.stateHash)}</span> },
                        ]}
                    />
                    <h3 className="fi-h3">Risk breaches</h3>
                    <StringList items={state.riskBreaches} empty="No active breaches." />
                </Panel>
            </div>

            <Panel title="Positions" icon="fa-layer-group">
                {positions.length === 0 ? <p className="fi-muted-note">No bond positions (all cash).</p> : (
                    <div className="fi-table-wrap">
                        <table className="fi-table">
                            <thead><tr><th>Security</th><th>Settled face</th><th>Economic face</th><th>Lots</th></tr></thead>
                            <tbody>
                                {positions.map(pos => (
                                    <tr key={pos.securityId}>
                                        <td><Link to={`/fi/instruments/${encodeURIComponent(pos.securityId)}`} className="mono">{pos.securityId}</Link></td>
                                        <td className="mono">{fmtFace(pos.settledFace)}</td>
                                        <td className="mono" title="Includes traded but unsettled face">{fmtFace(pos.economicFace)}</td>
                                        <td className="fi-small">
                                            {(pos.lots ?? []).map(l => (
                                                <div key={l.lotId} className="mono">{l.lotId}: {fmtFace(l.face)} @ {fmtPrice(l.cleanPricePer100)} (trade {l.tradeDate}, settle {l.settlementDate})</div>
                                            ))}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
                <p className="fi-muted-note">Economic face includes executed trades awaiting settlement; settled face is delivered.</p>
            </Panel>

            <div className="fi-two-col">
                <Panel title="Pending orders" icon="fa-hourglass-half">
                    {(state.openOrders ?? []).length === 0 ? <p className="fi-muted-note">No open orders.</p> : (
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Order</th><th>Side / face</th><th>Eligible session</th><th>Expires</th><th>Reserved cash</th></tr></thead>
                            <tbody>
                                {(state.openOrders ?? []).map(o => (
                                    <tr key={o.orderId}>
                                        <td className="mono fi-small">{o.orderId}<div><Link to={`/fi/decisions/${encodeURIComponent(o.decisionId)}`}>decision</Link></div></td>
                                        <td>{o.side} {o.securityId}<div className="mono fi-small">{fmtFace(o.face)}</div></td>
                                        <td><SessionDate value={o.eligibleSessionDate} /></td>
                                        <td><Instant value={o.expiresAt} context="market" /></td>
                                        <td className="mono">{fmtUsd(o.reservedCashUsd)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Panel>
                <Panel title="Settlement obligations" icon="fa-handshake">
                    {(state.pendingSettlements ?? []).length === 0 ? <p className="fi-muted-note">No pending settlements.</p> : (
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Settlement date</th><th>Security</th><th>Side / face</th><th>Cash</th></tr></thead>
                            <tbody>
                                {(state.pendingSettlements ?? []).map(s => (
                                    <tr key={s.settlementId}>
                                        <td><SessionDate value={s.settlementDate} label="settlement date" /></td>
                                        <td className="mono">{s.securityId}</td>
                                        <td>{s.side} <span className="mono fi-small">{fmtFace(s.face)}</span></td>
                                        <td className="mono">
                                            {fmtUsd(s.cashUsd)}
                                            <div className="fi-small">{s.side === 'BUY' ? 'payable on settlement' : s.side === 'SELL' ? 'receivable on settlement' : DASH}</div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Panel>
            </div>

            <PaymentCalendar portfolio={p} />
            <ValuationHistory portfolioId={p.portfolioId} />
            <OrdersPanel portfolioId={p.portfolioId} />
            <JournalPanel portfolioId={p.portfolioId} />
        </>
    );
}

function PaymentCalendar({ portfolio }: { portfolio: Portfolio }) {
    const view = portfolio.paymentCalendar;
    const calendar = view?.calendar;
    const items = calendar?.items ?? [];
    return (
        <Panel title="Payment calendar" icon="fa-calendar-alt">
            <p className="fi-muted-note">
                Upcoming contractual coupons and redemptions of held and unsettled securities, projected by the research
                engine from the current state. {calendar?.entitlementRule ? `Entitlement: ${calendar.entitlementRule}.` : ''}{' '}
                {calendar?.note ?? 'Projection only; not committed cash flows.'}
            </p>
            {view?.status === 'no_holdings' && <p className="fi-muted-note">No positions or pending settlements, so no scheduled payments.</p>}
            {view?.status === 'unavailable' && (
                <p className="fi-muted-note"><i className="fas fa-info-circle"></i> Payment calendar unavailable: {humanize(view.unavailableReason ?? 'unknown')}</p>
            )}
            {calendar && (
                <p className="fi-small">
                    Window {calendar.after ?? DASH} → {calendar.through ?? DASH}
                    {calendar.cashFlowsProcessedThrough && <> · cash flows processed through <SessionDate value={calendar.cashFlowsProcessedThrough} /></>}
                    {calendar.totals && <> · projected total <span className="mono">{fmtUsd(calendar.totals.totalUsd)}</span> (coupons {fmtUsd(calendar.totals.couponsUsd)}, redemptions {fmtUsd(calendar.totals.redemptionsUsd)})</>}
                </p>
            )}
            {view?.status === 'available' && items.length === 0 && <p className="fi-muted-note">No payments fall in the projection window.</p>}
            {items.length > 0 && (
                <div className="fi-table-wrap">
                    <table className="fi-table fi-table-dense">
                        <thead><tr><th>Payment date</th><th>Security</th><th>Kind</th><th>Amount per 100</th><th>Projected entitled face</th><th>Projected amount</th></tr></thead>
                        <tbody>
                            {items.map((cf, i) => (
                                <tr key={`${cf.securityId}-${cf.paymentDate}-${cf.kind}-${i}`}>
                                    <td><SessionDate value={cf.paymentDate} label="payment date" /></td>
                                    <td>
                                        <Link to={`/fi/instruments/${encodeURIComponent(cf.securityId)}`} className="mono">{cf.securityId}</Link>
                                        {cf.synthetic && <> <Tag tone="muted">synthetic</Tag></>}
                                    </td>
                                    <td>{humanize(cf.kind)}</td>
                                    <td className="mono">{fmtPrice(cf.amountPer100, 6)}</td>
                                    <td className="mono">{fmtFace(cf.projectedEntitledFaceUsd)}</td>
                                    <td className="mono">{fmtUsd(cf.projectedAmountUsd)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </Panel>
    );
}

function ValuationHistory({ portfolioId }: { portfolioId: string }) {
    const [page, setPage] = useState(1);
    const [expanded, setExpanded] = useState<string | null>(null);
    const query = useValuations(portfolioId, page, 50);
    return (
        <Panel title="Valuation history" icon="fa-chart-line">
            <QueryState query={query} label="valuations" isEmpty={d => d.items.length === 0} emptyMessage="No saved valuations yet.">
                {data => (
                    <>
                        <EquityCurves series={[{ key: 'equity', label: 'Equity (reconciled NAV)', color: '#3987e5', valuations: data.items }]} height={220} />
                        <div className="fi-table-wrap">
                            <table className="fi-table fi-table-dense">
                                <thead><tr><th>Valued at</th><th>Equity</th><th>Complete</th><th>Cash</th><th>Bonds</th><th>DV01</th><th>Mark policy</th><th></th></tr></thead>
                                <tbody>
                                    {data.items.map(v => (
                                        <ValuationRow key={v.valuationId} v={v} open={expanded === v.valuationId}
                                            onToggle={() => setExpanded(expanded === v.valuationId ? null : v.valuationId)} />
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <Pagination page={data.page} pageSize={data.pageSize} totalCount={data.totalCount} onPage={setPage} label="valuations" />
                    </>
                )}
            </QueryState>
        </Panel>
    );
}

function ValuationRow({ v, open, onToggle }: { v: Valuation; open: boolean; onToggle: () => void }) {
    const marks = v.detail?.marks ?? [];
    return (
        <>
            <tr>
                <td><Instant value={v.valuationAt} context="market" inline /></td>
                <td className="mono">{fmtUsd(v.equityUsd)}</td>
                <td>
                    <PassFail passed={v.complete} label={v.complete ? 'complete' : 'incomplete'} />
                    {!v.complete && v.incompleteReasons.length > 0 && <div className="fi-small fi-warn-text">{v.incompleteReasons.join('; ')}</div>}
                </td>
                <td className="mono">{fmtUsd(v.cashUsd)}</td>
                <td className="mono">{fmtUsd(v.bondValueUsd)}</td>
                <td className="mono">{fmtUsd(v.parallelDv01Usd)}</td>
                <td className="fi-small">{v.markPolicy}</td>
                <td>{marks.length > 0 && <button className="fi-link-button" onClick={onToggle}>{open ? 'hide marks' : `${marks.length} marks`}</button>}</td>
            </tr>
            {open && (
                <tr className="fi-subrow">
                    <td colSpan={8}>
                        <table className="fi-table fi-table-dense">
                            <thead><tr><th>Security</th><th>Mark type</th><th>Clean / accrued per 100</th><th>PV dirty</th><th>Observed</th><th>Age (bd)</th><th>Stale</th></tr></thead>
                            <tbody>
                                {marks.map(m => (
                                    <tr key={m.securityId}>
                                        <td className="mono">{m.securityId}</td>
                                        <td>{m.markType === 'curve_model' ? <ValueKindTag kind="model" /> : m.markType === 'unavailable' ? <Tag tone="fail">unavailable</Tag> : <ValueKindTag kind="quote" />}<div className="fi-small">{m.markType}</div></td>
                                        <td className="mono">{fmtPrice(m.cleanPricePer100)} / {fmtPrice(m.accruedPer100, 6)}</td>
                                        <td className="mono">{fmtUsd(m.pvDirtyUsd)}</td>
                                        <td><Instant value={m.observedAt} context="market" inline /></td>
                                        <td className="mono">{m.markAgeBusinessDays ?? DASH}</td>
                                        <td>{m.stale ? <Tag tone="warn">stale</Tag> : <span className="fi-muted">no</span>}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        <div className="fi-small">Calculation ids: <IdList ids={v.detail?.calculationIds} /></div>
                    </td>
                </tr>
            )}
        </>
    );
}

function OrdersPanel({ portfolioId }: { portfolioId: string }) {
    const [page, setPage] = useState(1);
    const [status, setStatus] = useState('');
    const query = useOrders(portfolioId, { page, pageSize: 50, status: status || undefined });
    return (
        <Panel title="Orders" icon="fa-exchange-alt">
            <div className="fi-filters">
                <label>Status
                    <select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
                        <option value="">All</option>
                        {ORDER_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </label>
            </div>
            <QueryState query={query} label="orders" isEmpty={d => d.items.length === 0} emptyMessage="No orders.">
                {data => (
                    <>
                        <OrdersTable orders={data.items} />
                        <Pagination page={data.page} pageSize={data.pageSize} totalCount={data.totalCount} onPage={setPage} label="orders" />
                    </>
                )}
            </QueryState>
        </Panel>
    );
}

function JournalPanel({ portfolioId }: { portfolioId: string }) {
    const [page, setPage] = useState(1);
    const [account, setAccount] = useState('');
    const [eventType, setEventType] = useState('');
    const query = useJournal(portfolioId, { page, pageSize: 25, account: account || undefined, eventType: eventType || undefined });
    return (
        <Panel title="Journal" icon="fa-book">
            <div className="fi-filters">
                <label>Account
                    <input type="text" value={account} placeholder="e.g. CASH" onChange={e => { setAccount(e.target.value.toUpperCase()); setPage(1); }} />
                </label>
                <label>Event type
                    <select value={eventType} onChange={e => { setEventType(e.target.value); setPage(1); }}>
                        <option value="">All</option>
                        {['capital_flow', 'settlement_due', 'redemption', 'coupon_payment', 'execution_observation', 'order_expiry', 'valuation_mark', 'order_cancellation', 'orders_submitted'].map(t => (
                            <option key={t} value={t}>{humanize(t)}</option>
                        ))}
                    </select>
                </label>
            </div>
            <QueryState query={query} label="journal entries" isEmpty={d => d.items.length === 0} emptyMessage="No journal entries match.">
                {data => (
                    <>
                        <div className="fi-journal">
                            {data.items.map(j => (
                                <div key={j.journalId} className="fi-journal-entry">
                                    <div className="fi-journal-head">
                                        <Tag tone="muted">{humanize(j.eventType)}</Tag>
                                        <Instant value={j.effectiveAt} context="market" inline />
                                        <span className="fi-small mono">v{j.committedVersion} · {j.template} · {j.journalId}</span>
                                    </div>
                                    <table className="fi-table fi-table-dense">
                                        <thead><tr><th>Account</th><th>Security</th><th>Debit</th><th>Credit</th><th>Memo</th></tr></thead>
                                        <tbody>
                                            {j.lines.map(l => (
                                                <tr key={l.lineId}>
                                                    <td className="mono">{l.account}</td>
                                                    <td className="mono">{l.securityId ?? DASH}</td>
                                                    <td className="mono">{Number(l.debitUsd) ? fmtUsd(l.debitUsd) : ''}</td>
                                                    <td className="mono">{Number(l.creditUsd) ? fmtUsd(l.creditUsd) : ''}</td>
                                                    <td className="fi-small">{l.memo}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            ))}
                        </div>
                        <Pagination page={data.page} pageSize={data.pageSize} totalCount={data.totalCount} onPage={setPage} label="journal entries" />
                    </>
                )}
            </QueryState>
        </Panel>
    );
}
