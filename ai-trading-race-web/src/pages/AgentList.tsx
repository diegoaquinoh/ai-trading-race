import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAgents } from '../hooks/useApi';
import { LoadingSpinner, ConnectionBanner, ServerUnavailable } from '../components';
import { isDev } from '../config/env';
import type { AgentSummary } from '../types';
import './AgentList.css';

const FALLBACK_AGENTS: AgentSummary[] = [
    { id: 'ph-1', name: 'Agent Alpha', strategy: 'Momentum Strategy', isActive: true, totalValue: 100000, percentChange: 0, lastUpdated: new Date().toISOString() },
    { id: 'ph-2', name: 'Agent Beta', strategy: 'Mean Reversion', isActive: true, totalValue: 100000, percentChange: 0, lastUpdated: new Date().toISOString() },
    { id: 'ph-3', name: 'Agent Gamma', strategy: 'ML Ensemble', isActive: false, totalValue: 100000, percentChange: 0, lastUpdated: new Date().toISOString() },
];

type StatusFilter = 'all' | 'active' | 'inactive';

export function AgentList() {
    const { data: agents, isLoading, error, refetch, isFetching } = useAgents();
    const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
    const [searchQuery, setSearchQuery] = useState('');

    // Use fallback data when the query has errored (dev only)
    const displayAgents = useMemo(
        () => agents ?? (isDev && error ? FALLBACK_AGENTS : []),
        [agents, error]
    );

    // Filter agents based on status and search
    const filteredAgents = useMemo(() => {
        if (!displayAgents.length) return [];

        return displayAgents.filter(agent => {
            // Status filter
            if (statusFilter === 'active' && !agent.isActive) return false;
            if (statusFilter === 'inactive' && agent.isActive) return false;

            // Search filter
            if (searchQuery && !agent.name.toLowerCase().includes(searchQuery.toLowerCase())) {
                return false;
            }

            return true;
        });
    }, [displayAgents, statusFilter, searchQuery]);

    if (isLoading && !agents) {
        return (
            <div className="agent-list-loading">
                <LoadingSpinner size="lg" message="Loading agents..." />
            </div>
        );
    }

    // In production, show a full error state when the server is unreachable and there's no cached data
    if (!isDev && error && !agents) {
        return (
            <div className="agent-list-page">
                <header className="page-header">
                    <h1><i className="fas fa-robot"></i> AI Agents</h1>
                    <p className="page-subtitle">Manage and monitor your trading agents</p>
                </header>
                <ServerUnavailable
                    title="Server Unavailable"
                    message="Unable to load agents. The server may be down or experiencing issues. Please try again shortly."
                    onRetry={() => refetch()}
                    isRetrying={isFetching}
                />
            </div>
        );
    }

    return (
        <div className="agent-list-page">
            <header className="page-header">
                <h1><i className="fas fa-robot"></i> AI Agents</h1>
                <p className="page-subtitle">Manage and monitor your trading agents</p>
            </header>

            {/* Connection Banner */}
            <ConnectionBanner 
                error={error} 
                onRetry={() => refetch()} 
                isRetrying={isFetching} 
            />

            {/* Filters */}
            <section className="filters-section">
                <div className="filters-row">
                    <div className="search-box">
                        <input
                            type="text"
                            placeholder="Search agents..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="search-input"
                        />
                    </div>

                    <div className="filter-group">
                        <label>Status:</label>
                        <select 
                            value={statusFilter} 
                            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                            className="filter-select"
                        >
                            <option value="all">All</option>
                            <option value="active">Active</option>
                            <option value="inactive">Inactive</option>
                        </select>
                    </div>
                </div>

                <div className="filter-summary">
                    Showing {filteredAgents.length} of {displayAgents.length} agents
                </div>
            </section>

            {/* Agents Grid */}
            <section className="agents-grid-section">
                <div className="agents-grid">
                    {filteredAgents.map((agent) => (
                        <Link 
                            key={agent.id} 
                            to={`/agents/${agent.id}`}
                            className="agent-card"
                        >
                            <div className="agent-card-header">
                                <h3>{agent.name}</h3>
                                <span className={`status-badge ${agent.isActive ? 'active' : 'inactive'}`}>
                                    {agent.isActive ? 'Active' : 'Inactive'}
                                </span>
                            </div>

                            <div className="agent-card-body">
                                <p className="agent-strategy">{agent.strategy}</p>
                                <div className="agent-value">
                                    <span className="value-label">Portfolio Value</span>
                                    <span className="value-amount">
                                        ${agent.totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </span>
                                    <span className={`value-change ${agent.percentChange >= 0 ? 'positive' : 'negative'}`}>
                                        {agent.percentChange >= 0 ? '+' : ''}{agent.percentChange.toFixed(2)}%
                                    </span>
                                </div>
                            </div>

                            <div className="agent-card-footer">
                                <span className="last-updated">
                                    Updated {new Date(agent.lastUpdated).toLocaleString()}
                                </span>
                                <span className="view-link">View Details <i className="fas fa-arrow-right"></i></span>
                            </div>
                        </Link>
                    ))}
                </div>

                {filteredAgents.length === 0 && (
                    <div className="empty-state">
                        <p>No agents found matching your criteria.</p>
                        <button onClick={() => {
                            setStatusFilter('all');
                            setSearchQuery('');
                        }}>
                            Clear Filters
                        </button>
                    </div>
                )}
            </section>
        </div>
    );
}
