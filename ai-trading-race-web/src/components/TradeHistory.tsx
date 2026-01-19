import { useState } from 'react';
import type { Trade } from '../types';
import './TradeHistory.css';

interface TradeHistoryProps {
    trades: Trade[];
    pageSize?: number;
}

export function TradeHistory({ trades, pageSize = 10 }: TradeHistoryProps) {
    const [currentPage, setCurrentPage] = useState(1);
    const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all');

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
                    </tr>
                </thead>
                <tbody>
                    {paginatedTrades.map((trade) => (
                        <tr key={trade.id} className="trade-row">
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
                        </tr>
                    ))}
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
                        ← Prev
                    </button>
                    <span className="page-info">
                        Page {currentPage} of {totalPages}
                    </span>
                    <button 
                        onClick={() => goToPage(currentPage + 1)} 
                        disabled={currentPage === totalPages}
                        className="page-btn"
                    >
                        Next →
                    </button>
                </div>
            )}
        </div>
    );
}
