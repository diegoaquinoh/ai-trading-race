import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAgents } from '../hooks/useApi';
import { LoadingSpinner, ErrorMessage } from '../components';
import './AgentList.css';

type StatusFilter = 'all' | 'active' | 'inactive';

export function AgentList() {
    const { data: agents, isLoading, error, refetch } = useAgents();
    const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
    const [searchQuery, setSearchQuery] = useState('');

    // Filter agents based on status and search
    const filteredAgents = useMemo(() => {
        if (!agents) return [];

        return agents.filter(agent => {
            // Status filter
            if (statusFilter === 'active' && !agent.isActive) return false;
            if (statusFilter === 'inactive' && agent.isActive) return false;

            // Search filter
            if (searchQuery && !agent.name.toLowerCase().includes(searchQuery.toLowerCase())) {
                return false;
            }

            return true;
        });
    }, [agents, statusFilter, searchQuery]);

    if (isLoading) {
        return (
            <div className="agent-list-loading">
                <LoadingSpinner size="lg" message="Loading agents..." />
            </div>
        );
    }

    if (error) {
        return (
            <ErrorMessage
                title="Failed to load agents"
                message={error.message}
                retryAction={() => refetch()}
                backLink="/"
            />
        );
    }

    return (
        <div className="agent-list-page">
            <header className="page-header">
                <h1>🤖 AI Agents</h1>
                <p className="page-subtitle">Manage and monitor your trading agents</p>
            </header>

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
                    Showing {filteredAgents.length} of {agents?.length ?? 0} agents
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
                                <span className="view-link">View Details →</span>
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
