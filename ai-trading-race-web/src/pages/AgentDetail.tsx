import { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAgent, useEquity, useTrades, usePortfolio } from '../hooks/useApi';
import { StatCard, EquityChart, TradeHistory } from '../components';
import type { AgentDetail as AgentDetailType, Portfolio } from '../types';
import './AgentDetail.css';

type PeriodFilter = '1H' | '6H' | '1D' | '7D' | '30D' | 'ALL';

export function AgentDetail() {
    const { id } = useParams<{ id: string }>();
    const { data: agent, isLoading: agentLoading, error: agentError } = useAgent(id!) as { 
        data: AgentDetailType | undefined, 
        isLoading: boolean, 
        error: Error | null 
    };
    const { data: equity, isLoading: equityLoading } = useEquity(id!);
    const { data: trades, isLoading: tradesLoading } = useTrades(id!);
    const { data: portfolio } = usePortfolio(id!) as { data: Portfolio | undefined };
    
    const [period, setPeriod] = useState<PeriodFilter>('ALL');

    // Filter equity data by period
    const filteredEquity = useMemo(() => {
        if (!equity) return [];
        
        const now = new Date();
        let cutoffDate: Date;
        
        switch (period) {
            case '1H':
                cutoffDate = new Date(now.getTime() - 60 * 60 * 1000);
                break;
            case '6H':
                cutoffDate = new Date(now.getTime() - 6 * 60 * 60 * 1000);
                break;
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
        
        return equity.filter(e => new Date(e.capturedAt) >= cutoffDate);
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
            initialValue: perf?.initialValue ?? 100000,
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
                        value={`$${(portfolio?.totalValue ?? metrics.currentValue).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                    />
                    <StatCard
                        icon="📈"
                        title="Performance"
                        value={`${(() => {
                            // Calculate live performance if portfolio data is available
                            const val = portfolio?.totalValue ?? metrics.currentValue;
                            const initial = metrics.initialValue || 100000;
                            const perf = ((val - initial) / initial) * 100;
                            return (perf >= 0 ? '+' : '') + perf.toFixed(2);
                        })()}%`}
                        trend={((portfolio?.totalValue ?? metrics.currentValue) >= metrics.initialValue) ? 'up' : 'down'}
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
                <div className="portfolio-summary">
                    <div className="portfolio-item">
                        <span className="label">Cash</span>
                        <span className="value">${(portfolio?.cash ?? metrics.cashValue).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                    </div>
                    <div className="portfolio-item">
                        <span className="label">Positions Value</span>
                        <span className="value">${metrics.positionsValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                    </div>
                    <div className="portfolio-item">
                        <span className="label">Total Value</span>
                        <span className="value">${(portfolio?.totalValue ?? metrics.currentValue).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                    </div>
                </div>
                
                {/* Positions Table */}
                {portfolio?.positions && portfolio.positions.length > 0 && (
                    <div className="positions-container">
                        <h3>📊 Holdings</h3>
                        <table className="positions-table">
                            <thead>
                                <tr>
                                    <th>Asset</th>
                                    <th>Quantity</th>
                                    <th>Avg Price</th>
                                    <th>Current Price</th>
                                    <th>Value</th>
                                    <th>Unrealized P&L</th>
                                </tr>
                            </thead>
                            <tbody>
                                {portfolio.positions.map((pos) => {
                                    const value = pos.quantity * pos.currentPrice;
                                    const cost = pos.quantity * pos.averagePrice;
                                    const pnl = value - cost;
                                    const pnlPercent = cost > 0 ? (pnl / cost) * 100 : 0;
                                    return (
                                        <tr key={pos.assetSymbol}>
                                            <td className="asset-symbol">{pos.assetSymbol}</td>
                                            <td>{pos.quantity.toFixed(6)}</td>
                                            <td>${pos.averagePrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                            <td>${pos.currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                            <td>${value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                            <td className={pnl >= 0 ? 'positive' : 'negative'}>
                                                {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} ({pnlPercent.toFixed(2)}%)
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
                
                {(!portfolio?.positions || portfolio.positions.length === 0) && (
                    <p className="no-positions">No open positions</p>
                )}
            </section>

            {/* Equity Chart with Period Selector */}
            <section className="chart-section">
                <div className="section-header">
                    <h2>📈 Equity Curve</h2>
                    <div className="period-selector">
                        {(['1H', '6H', '1D', '7D', '30D', 'ALL'] as PeriodFilter[]).map(p => (
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
