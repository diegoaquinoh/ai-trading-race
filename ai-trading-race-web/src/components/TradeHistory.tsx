import { useState, useMemo } from 'react';
import type { Trade, DecisionLog } from '../types';
import './TradeHistory.css';

interface TradeHistoryProps {
    trades: Trade[];
    decisions?: DecisionLog[];
    pageSize?: number;
}

/**
 * Find the closest decision log for a given trade by matching action, asset,
 * and picking the decision with the nearest timestamp (within a 5-minute window).
 */
function findMatchingDecision(trade: Trade, decisions: DecisionLog[]): DecisionLog | null {
    const tradeTime = new Date(trade.executedAt).getTime();
    const maxDelta = 5 * 60 * 1000; // 5 minutes

    let best: DecisionLog | null = null;
    let bestDelta = Infinity;

    for (const d of decisions) {
        if (d.action.toLowerCase() !== trade.side.toLowerCase()) continue;
        if (d.asset && d.asset.toUpperCase() !== trade.assetSymbol.toUpperCase()) continue;

        const delta = Math.abs(new Date(d.timestamp).getTime() - tradeTime);
        if (delta < bestDelta && delta <= maxDelta) {
            bestDelta = delta;
            best = d;
        }
    }
    return best;
}

export function TradeHistory({ trades, decisions = [], pageSize = 10 }: TradeHistoryProps) {
    const [currentPage, setCurrentPage] = useState(1);
    const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all');
    const [expandedId, setExpandedId] = useState<string | null>(null);

    // Pre-compute trade → decision mapping
    const decisionByTradeId = useMemo(() => {
        if (decisions.length === 0) return new Map<string, DecisionLog>();
        const map = new Map<string, DecisionLog>();
        for (const trade of trades) {
            const match = findMatchingDecision(trade, decisions);
            if (match) map.set(trade.id, match);
        }
        return map;
    }, [trades, decisions]);

    // Filter trades
    const filteredTrades = trades.filter(trade => {
        if (filter === 'all') return true;
        return trade.side.toLowerCase() === filter;
    });

    // Pagination
    const totalPages = Math.ceil(filteredTrades.length / pageSize);
    const startIndex = (currentPage - 1) * pageSize;
    const paginatedTrades = filteredTrades.slice(startIndex, startIndex + pageSize);

    const goToPage = (page: number) => {
        setCurrentPage(Math.max(1, Math.min(page, totalPages)));
    };

    if (trades.length === 0) {
        return (
            <div className="trade-history-empty">
                <p>No trades executed yet</p>
            </div>
        );
    }

    return (
        <div className="trade-history">
            {/* Filter bar */}
            <div className="trade-filter-bar">
                <div className="trade-filters">
                    <button 
                        className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
                        onClick={() => { setFilter('all'); setCurrentPage(1); }}
                    >
                        All ({trades.length})
                    </button>
                    <button 
                        className={`filter-btn buy ${filter === 'buy' ? 'active' : ''}`}
                        onClick={() => { setFilter('buy'); setCurrentPage(1); }}
                    >
                        Buy ({trades.filter(t => t.side.toLowerCase() === 'buy').length})
                    </button>
                    <button 
                        className={`filter-btn sell ${filter === 'sell' ? 'active' : ''}`}
                        onClick={() => { setFilter('sell'); setCurrentPage(1); }}
                    >
                        Sell ({trades.filter(t => t.side.toLowerCase() === 'sell').length})
                    </button>
                </div>
            </div>

            {/* Trades table */}
            <table className="trades-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Action</th>
                        <th>Asset</th>
                        <th>Quantity</th>
                        <th>Price</th>
                        <th>Value</th>
                        {decisions.length > 0 && <th>Rationale</th>}
                        {decisions.length > 0 && <th></th>}
                    </tr>
                </thead>
                <tbody>
                    {paginatedTrades.map((trade) => {
                        const decision = decisionByTradeId.get(trade.id);
                        const isExpanded = expandedId === trade.id;
                        const ruleIds: string[] = decision
                            ? (() => { try { return JSON.parse(decision.citedRuleIds) || []; } catch { return []; } })()
                            : [];

                        return (
                            <tr
                                key={trade.id}
                                className={`trade-row ${decision ? 'has-rationale' : ''} ${isExpanded ? 'expanded' : ''}`}
                                onClick={() => decision && setExpandedId(isExpanded ? null : trade.id)}
                            >
                                <td className="trade-time">
                                    {new Date(trade.executedAt).toLocaleString()}
                                </td>
                                <td className={`trade-action ${trade.side.toLowerCase()}`}>
                                    <span className="action-badge">
                                        {trade.side.toUpperCase()}
                                    </span>
                                </td>
                                <td className="trade-asset">{trade.assetSymbol}</td>
                                <td className="trade-qty">
                                    {trade.quantity.toFixed(6)}
                                </td>
                                <td className="trade-price">
                                    ${trade.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                </td>
                                <td className="trade-value">
                                    ${(trade.totalValue ?? trade.quantity * trade.price).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                </td>
                                {decisions.length > 0 && (
                                    <td className="trade-rationale">
                                        {decision ? (
                                            isExpanded ? (
                                                <div className="rationale-expanded">
                                                    <p>{decision.rationale}</p>
                                                    {ruleIds.length > 0 && (
                                                        <div className="cited-rules">
                                                            <span className="rules-label">Rules:</span>
                                                            {ruleIds.map(rule => (
                                                                <span key={rule} className="rule-tag">{rule}</span>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            ) : (
                                                <span className="rationale-truncated">
                                                    {decision.rationale.length > 60
                                                        ? decision.rationale.slice(0, 60) + '...'
                                                        : decision.rationale}
                                                </span>
                                            )
                                        ) : (
                                            <span className="rationale-none">-</span>
                                        )}
                                    </td>
                                )}
                                {decisions.length > 0 && (
                                    <td className="trade-expand">
                                        {decision && (
                                            <span className="expand-icon">{isExpanded ? '\u25B2' : '\u25BC'}</span>
                                        )}
                                    </td>
                                )}
                            </tr>
                        );
                    })}
                </tbody>
            </table>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="trade-pagination">
                    <button 
                        onClick={() => goToPage(currentPage - 1)} 
                        disabled={currentPage === 1}
                        className="page-btn"
                    >
                        <i className="fas fa-arrow-left"></i> Prev
                    </button>
                    <span className="page-info">
                        Page {currentPage} of {totalPages}
                    </span>
                    <button 
                        onClick={() => goToPage(currentPage + 1)} 
                        disabled={currentPage === totalPages}
                        className="page-btn"
                    >
                        Next <i className="fas fa-arrow-right"></i>
                    </button>
                </div>
            )}
        </div>
    );
}
