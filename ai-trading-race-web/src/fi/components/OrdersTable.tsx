import { Link } from 'react-router-dom';
import type { Order } from '../api/types';
import { fmtFace, fmtPrice, fmtUsd } from '../lib/format';
import { Tag, ValueKindTag } from './Badges';
import { Instant, SessionDate } from './Instant';

export function OrdersTable({ orders }: { orders: Order[] }) {
    return (
        <div className="fi-table-wrap">
            <table className="fi-table fi-table-dense">
                <thead>
                    <tr><th>Order</th><th>Side / security / face</th><th>Submitted</th><th>Eligible session / expiry</th><th>Status</th><th>Fill</th></tr>
                </thead>
                <tbody>
                    {orders.map(o => (
                        <tr key={o.orderId}>
                            <td className="mono fi-small">
                                {o.orderId}
                                {o.bootstrap && <div><Tag tone="muted">bootstrap</Tag></div>}
                                <div><Link to={`/fi/decisions/${encodeURIComponent(o.decisionId)}`}>decision</Link></div>
                            </td>
                            <td>{o.side} <span className="mono">{o.securityId}</span><div className="mono fi-small">{fmtFace(o.face)} · reserved {fmtUsd(o.reservedCashUsd)}</div></td>
                            <td><Instant value={o.submittedAt} context="market" /></td>
                            <td><SessionDate value={o.eligibleSessionDate} /><div className="fi-small">expires</div><Instant value={o.expiresAt} context="market" /></td>
                            <td>
                                <Tag tone={o.status === 'FILLED' ? 'ok' : o.status === 'ACCEPTED' ? 'neutral' : o.status === 'CANCELLED' ? 'muted' : 'fail'}>{o.status}</Tag>
                                {o.statusReason && <div className="fi-small fi-warn-text">{o.statusReason}</div>}
                            </td>
                            <td className="fi-small">
                                {o.fill ? (
                                    <>
                                        <Instant value={o.fill.executedAt} context="market" inline />
                                        <div>{o.fill.quoteKind === 'synthetic_model' ? <ValueKindTag kind="model" /> : <ValueKindTag kind="quote" />} {o.fill.quoteKind}</div>
                                        <div className="mono">ref {fmtPrice(o.fill.referenceCleanPricePer100)} → exec {fmtPrice(o.fill.executionCleanPricePer100)} · dirty {fmtPrice(o.fill.dirtyPricePer100)}</div>
                                        <div className="mono">consideration {fmtUsd(o.fill.considerationUsd)} · fees {fmtUsd(o.fill.feesUsd)}</div>
                                        <div>settles <SessionDate value={o.fill.settlementDate} /> · {o.fill.timingLabel}</div>
                                    </>
                                ) : <span className="fi-muted">no fill</span>}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
