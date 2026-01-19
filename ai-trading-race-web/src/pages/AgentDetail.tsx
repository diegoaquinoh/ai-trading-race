import { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAgent, useEquity, useTrades } from '../hooks/useApi';
import { StatCard, EquityChart, TradeHistory } from '../components';
import type { AgentDetail as AgentDetailType } from '../types';
import './AgentDetail.css';

type PeriodFilter = '1D' | '7D' | '30D' | 'ALL';

export function AgentDetail() {
    const { id } = useParams<{ id: string }>();
    const { data: agent, isLoading: agentLoading, error: agentError } = useAgent(id!) as { 
        data: AgentDetailType | undefined, 
        isLoading: boolean, 
        error: Error | null 
    };
    const { data: equity, isLoading: equityLoading } = useEquity(id!);
    const { data: trades, isLoading: tradesLoading } = useTrades(id!);
    
    const [period, setPeriod] = useState<PeriodFilter>('ALL');

    // Filter equity data by period
    const filteredEquity = useMemo(() => {
        if (!equity) return [];
        
        const now = new Date();
        let cutoffDate: Date;
        
        switch (period) {
            case '1D':
                cutoffDate = new Date(now.getTime() - 24 * 60 * 60 * 1000);
                break;
            case '7D':
                cutoffDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
                break;
            case '30D':
                cutoffDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
                break;
            default:
                return equity;
        }
        
        return equity.filter(e => new Date(e.timestamp) >= cutoffDate);
    }, [equity, period]);

    // Extract performance metrics from agent data
    const metrics = useMemo(() => {
        const perf = agent?.performance;
        const snapshot = agent?.latestSnapshot;
        
        return {
            currentValue: snapshot?.totalValue ?? perf?.currentValue ?? 100000,
            cashValue: snapshot?.cashValue ?? 0,
            positionsValue: snapshot?.positionsValue ?? 0,
            performance: perf?.percentReturn ?? snapshot?.percentChange ?? 0,
            maxDrawdown: perf?.maxDrawdown ?? 0,
            totalTrades: perf?.totalTrades ?? 0,
            winRate: perf?.winRate ?? 0,
            sharpeRatio: perf?.sharpeRatio ?? null,
        };
    }, [agent]);

    if (agentLoading || equityLoading) {
        return (
            <div className="loading">
                <div className="spinner"></div>
                <p>Loading agent details...</p>
            </div>
        );
    }

    if (agentError || !agent) {
        return (
            <div className="error">
                <p>Agent not found</p>
                <Link to="/agents">← Back to Agents</Link>
            </div>
        );
    }

    return (
        <div className="agent-detail">
            <nav className="breadcrumb">
                <Link to="/">Dashboard</Link> / <Link to="/agents">Agents</Link> / <span>{agent.name}</span>
            </nav>

            <header className="agent-header">
                <div className="agent-title">
                    <h1>{agent.name}</h1>
                    <span className={`status-badge ${agent.isActive ? 'active' : 'inactive'}`}>
                        {agent.isActive ? 'Active' : 'Inactive'}
                    </span>
                </div>
                <p className="agent-strategy">{agent.strategy}</p>
            </header>

            {/* Key Metrics */}
            <section className="metrics-section">
                <div className="metrics-grid">
                    <StatCard
                        icon="💰"
                        title="Portfolio Value"
                        value={`$${metrics.currentValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                    />
                    <StatCard
                        icon="📈"
                        title="Performance"
                        value={`${metrics.performance >= 0 ? '+' : ''}${metrics.performance.toFixed(2)}%`}
                        trend={metrics.performance >= 0 ? 'up' : 'down'}
                    />
                    <StatCard
                        icon="📉"
                        title="Max Drawdown"
                        value={`-${metrics.maxDrawdown.toFixed(2)}%`}
                        trend={metrics.maxDrawdown > 10 ? 'down' : 'neutral'}
                    />
                    <StatCard
                        icon="🔄"
                        title="Total Trades"
                        value={metrics.totalTrades}
                    />
                </div>
            </section>

            {/* Portfolio Breakdown */}
            <section className="portfolio-section">
                <h2>💼 Portfolio Breakdown</h2>
                <div className="portfolio-grid">
                    <div className="portfolio-item">
                        <span className="label">Cash</span>
                        <span className="value">${metrics.cashValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                    </div>
                    <div className="portfolio-item">
                        <span className="label">Positions</span>
                        <span className="value">${metrics.positionsValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                    </div>
                    <div className="portfolio-item">
                        <span className="label">Win Rate</span>
                        <span className="value">{(metrics.winRate * 100).toFixed(0)}%</span>
                    </div>
                    {metrics.sharpeRatio !== null && (
                        <div className="portfolio-item">
                            <span className="label">Sharpe Ratio</span>
                            <span className="value">{metrics.sharpeRatio.toFixed(2)}</span>
                        </div>
                    )}
                </div>
            </section>

            {/* Equity Chart with Period Selector */}
            <section className="chart-section">
                <div className="section-header">
                    <h2>📈 Equity Curve</h2>
                    <div className="period-selector">
                        {(['1D', '7D', '30D', 'ALL'] as PeriodFilter[]).map(p => (
                            <button
                                key={p}
                                className={`period-btn ${period === p ? 'active' : ''}`}
                                onClick={() => setPeriod(p)}
                            >
                                {p}
                            </button>
                        ))}
                    </div>
                </div>
                <EquityChart
                    agents={[{
                        agentId: agent.id,
                        agentName: agent.name,
                        data: filteredEquity
                    }]}
                    height={350}
                    showLegend={false}
                />
            </section>

            {/* Trade History */}
            <section className="trades-section">
                <h2>📋 Trade History</h2>
                {tradesLoading ? (
                    <div className="loading-inline">
                        <div className="spinner"></div>
                        <p>Loading trades...</p>
                    </div>
                ) : (
                    <TradeHistory trades={trades ?? []} pageSize={10} />
                )}
            </section>

            {/* Agent Info */}
            <section className="info-section">
                <h2>ℹ️ Agent Information</h2>
                <div className="info-grid">
                    <div className="info-item">
                        <span className="info-label">Agent ID</span>
                        <span className="info-value mono">{agent.id}</span>
                    </div>
                    <div className="info-item">
                        <span className="info-label">Created</span>
                        <span className="info-value">{new Date(agent.createdAt).toLocaleDateString()}</span>
                    </div>
                    <div className="info-item">
                        <span className="info-label">Status</span>
                        <span className={`info-value ${agent.isActive ? 'text-green' : 'text-muted'}`}>
                            {agent.isActive ? 'Active' : 'Inactive'}
                        </span>
                    </div>
                    {agent.performance && (
                        <div className="info-item">
                            <span className="info-label">Last Calculated</span>
                            <span className="info-value">{new Date(agent.performance.calculatedAt).toLocaleString()}</span>
                        </div>
                    )}
                </div>
            </section>
        </div>
    );
}
