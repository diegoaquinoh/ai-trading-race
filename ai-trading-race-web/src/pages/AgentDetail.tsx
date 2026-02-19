import { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAgent, useEquity, useTrades, usePortfolio, useDecisions } from '../hooks/useApi';
import { StatCard, EquityChart, TradeHistory, DecisionHistory, ConnectionBanner, ServerUnavailable } from '../components';
import { isDev } from '../config/env';
import type { AgentDetail as AgentDetailType, Portfolio } from '../types';
import './AgentDetail.css';

type PeriodFilter = '1H' | '6H' | '1D' | '7D' | '30D' | 'ALL';

export function AgentDetail() {
    const { id } = useParams<{ id: string }>();
    const { data: agent, isLoading: agentLoading, error: agentError, refetch, isFetching } = useAgent(id!) as { 
        data: AgentDetailType | undefined, 
        isLoading: boolean, 
        error: Error | null,
        refetch: () => void,
        isFetching: boolean,
    };
    const { data: equity } = useEquity(id!);
    const { data: trades, isLoading: tradesLoading } = useTrades(id!);
    const { data: portfolio } = usePortfolio(id!) as { data: Portfolio | undefined };
    const { data: decisions, isLoading: decisionsLoading } = useDecisions(id!);

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

    // Show spinner only on first load without any placeholder data
    if (agentLoading && !agent) {
        return (
            <div className="loading">
                <div className="spinner"></div>
                <p>Loading agent details...</p>
            </div>
        );
    }

    // In production, show a full error state when the server is unreachable and there's no cached data
    if (!isDev && agentError && !agent) {
        return (
            <div className="agent-detail">
                <nav className="breadcrumb">
                    <Link to="/">Dashboard</Link> / <Link to="/agents">Agents</Link> / <span>Agent</span>
                </nav>
                <ServerUnavailable
                    title="Agent Unavailable"
                    message="Unable to load agent details. The server may be down or experiencing issues. Please try again shortly."
                    onRetry={() => refetch()}
                    isRetrying={isFetching}
                />
            </div>
        );
    }

    // In dev, use placeholder data from the hook if agent is not available
    const displayAgent = agent ?? {
        id: id ?? 'unknown',
        name: 'Agent (offline)',
        strategy: '—',
        isActive: false,
        createdAt: new Date().toISOString(),
    };

    return (
        <div className="agent-detail">
            <nav className="breadcrumb">
                <Link to="/">Dashboard</Link> / <Link to="/agents">Agents</Link> / <span>{displayAgent.name}</span>
            </nav>

            {/* Connection Banner */}
            <ConnectionBanner 
                error={agentError} 
                onRetry={() => refetch()} 
                isRetrying={isFetching} 
            />

            <header className="agent-header">
                <div className="agent-title">
                    <h1>{displayAgent.name}</h1>
                    <span className={`status-badge ${displayAgent.isActive ? 'active' : 'inactive'}`}>
                        {displayAgent.isActive ? 'Active' : 'Inactive'}
                    </span>
                </div>
                <p className="agent-strategy">{displayAgent.strategy}</p>
            </header>

            {/* Key Metrics */}
            <section className="metrics-section">
                <div className="metrics-grid">
                    <StatCard
                        iconClass="fas fa-wallet"
                        title="Portfolio Value"
                        value={`$${(portfolio?.totalValue ?? metrics.currentValue).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                    />
                    <StatCard
                        iconClass="fas fa-chart-line"
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
                        iconClass="fas fa-arrow-down"
                        title="Max Drawdown"
                        value={`-${metrics.maxDrawdown.toFixed(2)}%`}
                        trend={metrics.maxDrawdown > 10 ? 'down' : 'neutral'}
                    />
                    <StatCard
                        iconClass="fas fa-exchange-alt"
                        title="Total Trades"
                        value={metrics.totalTrades}
                    />
                </div>
            </section>

            {/* Portfolio Breakdown */}
            <section className="portfolio-section">
                <h2><i className="fas fa-briefcase"></i> Portfolio Breakdown</h2>
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
                        <h3><i className="fas fa-th-list"></i> Holdings</h3>
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
                    <h2><i className="fas fa-chart-line"></i> Equity Curve</h2>
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
                        agentId: displayAgent.id,
                        agentName: displayAgent.name,
                        data: filteredEquity
                    }]}
                    height={350}
                    showLegend={false}
                />
            </section>

            {/* Trade History */}
            <section className="trades-section">
                <h2><i className="fas fa-history"></i> Trade History</h2>
                {tradesLoading ? (
                    <div className="loading-inline">
                        <div className="spinner"></div>
                        <p>Loading trades...</p>
                    </div>
                ) : (
                    <TradeHistory trades={trades ?? []} decisions={decisions ?? []} pageSize={10} />
                )}
            </section>

            {/* ML Decision Logs */}
            <section className="decisions-section">
                <h2>ML Decision Logs</h2>
                {decisionsLoading ? (
                    <div className="loading-inline">
                        <div className="spinner"></div>
                        <p>Loading decision logs...</p>
                    </div>
                ) : (
                    <DecisionHistory decisions={decisions ?? []} pageSize={10} />
                )}
            </section>

            {/* Agent Info */}
            <section className="info-section">
                <h2><i className="fas fa-info-circle"></i> Agent Information</h2>
                <div className="info-grid">
                    <div className="info-item">
                        <span className="info-label">Agent ID</span>
                        <span className="info-value mono">{displayAgent.id}</span>
                    </div>
                    <div className="info-item">
                        <span className="info-label">Created</span>
                        <span className="info-value">{new Date(displayAgent.createdAt).toLocaleDateString()}</span>
                    </div>
                    <div className="info-item">
                        <span className="info-label">Status</span>
                        <span className={`info-value ${displayAgent.isActive ? 'text-green' : 'text-muted'}`}>
                            {displayAgent.isActive ? 'Active' : 'Inactive'}
                        </span>
                    </div>
                    {agent?.performance && (
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
