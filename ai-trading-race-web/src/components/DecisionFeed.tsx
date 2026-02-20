import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { DecisionWithAgent } from '../hooks/useApi';
import './DecisionFeed.css';

interface DecisionFeedProps {
    decisions: DecisionWithAgent[];
    isLoading?: boolean;
}

function timeAgo(dateStr: string): string {
    const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

function parseJson(raw: string | null): string[] {
    if (!raw) return [];
    try { return JSON.parse(raw) || []; } catch { return []; }
}

export function DecisionFeed({ decisions, isLoading }: DecisionFeedProps) {
    const [expandedId, setExpandedId] = useState<number | null>(null);

    if (isLoading) {
        return (
            <div className="decision-feed-loading">
                <div className="spinner"></div>
                <p>Loading decisions...</p>
            </div>
        );
    }

    if (decisions.length === 0) {
        return (
            <div className="decision-feed-empty">
                <i className="fas fa-brain"></i>
                <p>No decisions recorded yet</p>
            </div>
        );
    }

    return (
        <div className="decision-feed">
            {decisions.map((decision, index) => {
                const impact = decision.portfolioValueAfter - decision.portfolioValueBefore;
                const isExpanded = expandedId === decision.id;
                const ruleIds = parseJson(decision.citedRuleIds);
                const errors = parseJson(decision.validationErrors);

                return (
                    <div
                        key={decision.id}
                        className={`feed-card ${isExpanded ? 'expanded' : ''}`}
                        style={{ animationDelay: `${index * 50}ms` }}
                        onClick={() => setExpandedId(isExpanded ? null : decision.id)}
                    >
                        <div className="feed-card-header">
                            <div className="feed-card-meta">
                                <span className="feed-agent-name">{decision.agentName}</span>
                                <span className={`feed-action-badge ${decision.action.toLowerCase()}`}>
                                    {decision.action.toUpperCase()}
                                </span>
                                {decision.asset && (
                                    <span className="feed-asset">{decision.asset}</span>
                                )}
                                <span className="feed-regime-badge">{decision.detectedRegime}</span>
                            </div>
                            <span className="feed-time">{timeAgo(decision.timestamp)}</span>
                        </div>

                        <p className="feed-rationale">{decision.rationale}</p>

                        <div className="feed-card-footer">
                            <span className={`feed-impact ${impact >= 0 ? 'positive' : 'negative'}`}>
                                {impact >= 0 ? '+' : ''}${impact.toFixed(2)}
                            </span>
                            <Link
                                to={`/agents/${decision.agentId}`}
                                className="feed-view-agent"
                                onClick={(e) => e.stopPropagation()}
                            >
                                View Agent <i className="fas fa-arrow-right"></i>
                            </Link>
                        </div>

                        {isExpanded && (ruleIds.length > 0 || errors.length > 0) && (
                            <div className="feed-expanded-details">
                                {ruleIds.length > 0 && (
                                    <div className="feed-rules">
                                        <span className="feed-detail-label">Rules:</span>
                                        {ruleIds.map(rule => (
                                            <span key={rule} className="rule-tag">{rule}</span>
                                        ))}
                                    </div>
                                )}
                                {errors.length > 0 && (
                                    <div className="feed-errors">
                                        <span className="feed-detail-label">Validation:</span>
                                        {errors.map((err, i) => (
                                            <span key={i} className="error-tag">{err}</span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
