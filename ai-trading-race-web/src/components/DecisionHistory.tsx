import { useState } from 'react';
import type { DecisionLog } from '../types';
import './DecisionHistory.css';

interface DecisionHistoryProps {
    decisions: DecisionLog[];
    pageSize?: number;
}

export function DecisionHistory({ decisions, pageSize = 10 }: DecisionHistoryProps) {
    const [currentPage, setCurrentPage] = useState(1);
    const [filter, setFilter] = useState<'all' | 'buy' | 'sell' | 'hold'>('all');
    const [expandedId, setExpandedId] = useState<number | null>(null);

    // Filter decisions
    const filteredDecisions = decisions.filter(decision => {
        if (filter === 'all') return true;
        return decision.action.toLowerCase() === filter;
    });

    // Pagination
    const totalPages = Math.ceil(filteredDecisions.length / pageSize);
    const startIndex = (currentPage - 1) * pageSize;
    const paginatedDecisions = filteredDecisions.slice(startIndex, startIndex + pageSize);

    const goToPage = (page: number) => {
        setCurrentPage(Math.max(1, Math.min(page, totalPages)));
    };

    // Parse JSON string fields safely
    const parseRuleIds = (raw: string): string[] => {
        try { return JSON.parse(raw) || []; } catch { return []; }
    };

    const parseValidationErrors = (raw: string | null): string[] => {
        if (!raw) return [];
        try { return JSON.parse(raw) || []; } catch { return []; }
    };

    if (decisions.length === 0) {
        return (
            <div className="decision-history-empty">
                <p>No decision logs available yet</p>
            </div>
        );
    }

    return (
        <div className="decision-history">
            {/* Filter bar */}
            <div className="decision-filter-bar">
                <div className="decision-filters">
                    <button
                        className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
                        onClick={() => { setFilter('all'); setCurrentPage(1); }}
                    >
                        All ({decisions.length})
                    </button>
                    <button
                        className={`filter-btn buy ${filter === 'buy' ? 'active' : ''}`}
                        onClick={() => { setFilter('buy'); setCurrentPage(1); }}
                    >
                        Buy ({decisions.filter(d => d.action.toLowerCase() === 'buy').length})
                    </button>
                    <button
                        className={`filter-btn sell ${filter === 'sell' ? 'active' : ''}`}
                        onClick={() => { setFilter('sell'); setCurrentPage(1); }}
                    >
                        Sell ({decisions.filter(d => d.action.toLowerCase() === 'sell').length})
                    </button>
                    <button
                        className={`filter-btn hold ${filter === 'hold' ? 'active' : ''}`}
                        onClick={() => { setFilter('hold'); setCurrentPage(1); }}
                    >
                        Hold ({decisions.filter(d => d.action.toLowerCase() === 'hold').length})
                    </button>
                </div>
            </div>

            {/* Decisions table */}
            <table className="decisions-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Action</th>
                        <th>Asset</th>
                        <th>Regime</th>
                        <th>Rationale</th>
                        <th>Impact</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {paginatedDecisions.map((decision) => {
                        const impact = decision.portfolioValueAfter - decision.portfolioValueBefore;
                        const ruleIds = parseRuleIds(decision.citedRuleIds);
                        const errors = parseValidationErrors(decision.validationErrors);
                        const isExpanded = expandedId === decision.id;

                        return (
                            <tr
                                key={decision.id}
                                className={`decision-row ${isExpanded ? 'expanded' : ''}`}
                                onClick={() => setExpandedId(isExpanded ? null : decision.id)}
                            >
                                <td className="decision-time">
                                    {new Date(decision.timestamp).toLocaleString()}
                                </td>
                                <td className={`decision-action ${decision.action.toLowerCase()}`}>
                                    <span className="action-badge">
                                        {decision.action.toUpperCase()}
                                    </span>
                                </td>
                                <td className="decision-asset">
                                    {decision.asset || '-'}
                                </td>
                                <td className="decision-regime">
                                    <span className="regime-badge">{decision.detectedRegime}</span>
                                </td>
                                <td className="decision-rationale">
                                    {isExpanded ? (
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
                                            {errors.length > 0 && (
                                                <div className="validation-errors">
                                                    <span className="errors-label">Validation:</span>
                                                    {errors.map((err, i) => (
                                                        <span key={i} className="error-tag">{err}</span>
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
                                    )}
                                </td>
                                <td className={`decision-impact ${impact >= 0 ? 'positive' : 'negative'}`}>
                                    {impact >= 0 ? '+' : ''}${impact.toFixed(2)}
                                </td>
                                <td className="decision-expand">
                                    <span className="expand-icon">{isExpanded ? '\u25B2' : '\u25BC'}</span>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="decision-pagination">
                    <button
                        onClick={() => goToPage(currentPage - 1)}
                        disabled={currentPage === 1}
                        className="page-btn"
                    >
                        Prev
                    </button>
                    <span className="page-info">
                        Page {currentPage} of {totalPages}
                    </span>
                    <button
                        onClick={() => goToPage(currentPage + 1)}
                        disabled={currentPage === totalPages}
                        className="page-btn"
                    >
                        Next
                    </button>
                </div>
            )}
        </div>
    );
}
