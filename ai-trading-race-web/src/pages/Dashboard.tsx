import { useCountdown } from '../hooks/useCountdown';
import { useLeaderboard, useMarketPrices, useAllAgentEquity, useAllAgentDecisions } from '../hooks/useApi';
import { StatCard, LeaderboardTable, EquityChart, MarketPrices, RefreshIndicator, LoadingSpinner, ConnectionBanner, ServerUnavailable, DecisionFeed } from '../components';
import { isVisibleModelType } from '../config/hiddenModels';
import { isDev } from '../config/env';
import type { LeaderboardEntry, MarketPrice } from '../types';
import './Dashboard.css';

// Fallback data shown ONLY in dev mode when the backend is unreachable
const FALLBACK_LEADERBOARD: LeaderboardEntry[] = [
    { agent: { id: 'ph-1', name: 'Agent Alpha', modelType: 'Placeholder', provider: 'Momentum Strategy', isActive: true, createdAt: new Date().toISOString() }, currentValue: 100000, performancePercent: 0, drawdown: 0 },
    { agent: { id: 'ph-2', name: 'Agent Beta', modelType: 'Placeholder', provider: 'Mean Reversion', isActive: true, createdAt: new Date().toISOString() }, currentValue: 100000, performancePercent: 0, drawdown: 0 },
    { agent: { id: 'ph-3', name: 'Agent Gamma', modelType: 'Placeholder', provider: 'ML Ensemble', isActive: false, createdAt: new Date().toISOString() }, currentValue: 100000, performancePercent: 0, drawdown: 0 },
];

const FALLBACK_PRICES: MarketPrice[] = [
    { symbol: 'BTC', name: 'Bitcoin', price: 0, change24h: 0, changePercent24h: 0, high24h: 0, low24h: 0, updatedAt: new Date().toISOString() },
    { symbol: 'ETH', name: 'Ethereum', price: 0, change24h: 0, changePercent24h: 0, high24h: 0, low24h: 0, updatedAt: new Date().toISOString() },
    { symbol: 'SOL', name: 'Solana', price: 0, change24h: 0, changePercent24h: 0, high24h: 0, low24h: 0, updatedAt: new Date().toISOString() },
];

export function Dashboard() {
    const { data: leaderboard, isLoading, error, dataUpdatedAt, isFetching, refetch } = useLeaderboard();
    const { data: marketPrices, isLoading: pricesLoading, error: pricesError } = useMarketPrices();
    const { data: equityData, isLoading: equityLoading } = useAllAgentEquity(leaderboard);
    const { data: allDecisions, isLoading: decisionsLoading } = useAllAgentDecisions(leaderboard);
    
    const lastUpdate = dataUpdatedAt ? new Date(dataUpdatedAt) : null;
    const { remaining: secondsUntilRefresh } = useCountdown(30, dataUpdatedAt);

    // Use fallback data when queries have errored and data is undefined (dev only)
    const allLeaderboard = leaderboard ?? (isDev && error ? FALLBACK_LEADERBOARD : []);
    // Hide agents whose model provider API key we don't have yet (see config/hiddenModels.ts)
    const displayLeaderboard = allLeaderboard.filter(e => isVisibleModelType(e.agent.modelType));
    const displayPrices = marketPrices ?? (isDev && pricesError ? FALLBACK_PRICES : []);

    // Only show equity curves for visible agents
    const visibleAgentIds = new Set(displayLeaderboard.map(e => e.agent.id));
    const displayEquity = equityData?.filter(d => visibleAgentIds.has(d.agentId));

    // Calculate stats from leaderboard
    const stats = calculateStats(displayLeaderboard);

    // Pick the first available error to display
    const displayError = error ?? pricesError ?? null;

    if (isLoading && !leaderboard) {
        return (
            <div className="dashboard-loading">
                <LoadingSpinner size="lg" message="Loading leaderboard..." />
            </div>
        );
    }

    // In production, show a full error state when the server is unreachable and there's no cached data
    if (!isDev && error && !leaderboard) {
        return (
            <div className="dashboard">
                <header className="dashboard-header">
                    <h1><i className="fas fa-flag-checkered"></i> AI Trading Race</h1>
                    <p className="subtitle">Watch AI agents compete in real-time crypto trading</p>
                </header>
                <ServerUnavailable
                    title="Server Unavailable"
                    message="Unable to load the leaderboard. The server may be down or experiencing issues. Please try again shortly."
                    onRetry={() => refetch()}
                    isRetrying={isFetching}
                />
            </div>
        );
    }

    return (
        <div className="dashboard">
            <header className="dashboard-header">
                <h1><i className="fas fa-flag-checkered"></i> AI Trading Race</h1>
                <p className="subtitle">Watch AI agents compete in real-time crypto trading</p>
            </header>

            {/* Connection Banner — shown when any query has an error */}
            <ConnectionBanner 
                error={displayError} 
                onRetry={() => refetch()} 
                isRetrying={isFetching} 
            />

            {/* Market Prices */}
            <section className="market-section">
                <h2><i className="fas fa-coins"></i> Market Prices</h2>
                <MarketPrices prices={displayPrices} isLoading={pricesLoading && !marketPrices} />
            </section>

            {/* Stats Cards */}
            <section className="stats-section">
                <div className="stats-grid">
                    <StatCard
                        iconClass="fas fa-trophy"
                        title="Best Performer"
                        value={stats.bestAgent?.name ?? 'N/A'}
                        trend={stats.bestPerformance >= 0 ? 'up' : 'down'}
                        trendValue={`${stats.bestPerformance >= 0 ? '+' : ''}${stats.bestPerformance.toFixed(2)}%`}
                    />
                    <StatCard
                        iconClass="fas fa-users"
                        title="Total Agents"
                        value={stats.totalAgents}
                        subtitle={`${stats.activeAgents} active`}
                    />
                    <StatCard
                        iconClass="fas fa-wallet"
                        title="Total AUM"
                        value={`$${(stats.totalValue / 1000).toFixed(0)}k`}
                        subtitle="Assets under management"
                    />
                    <StatCard
                        iconClass="fas fa-chart-line"
                        title="Avg Performance"
                        value={`${stats.avgPerformance >= 0 ? '+' : ''}${stats.avgPerformance.toFixed(2)}%`}
                        trend={stats.avgPerformance >= 0 ? 'up' : 'down'}
                    />
                </div>
            </section>

            {/* Leaderboard */}
            <section className="leaderboard-section">
                <div className="section-header">
                    <h2><i className="fas fa-list-ol"></i> Leaderboard</h2>
                    <RefreshIndicator 
                        lastUpdate={lastUpdate} 
                        isRefreshing={isFetching} 
                        nextRefreshIn={secondsUntilRefresh}
                    />
                </div>
                <LeaderboardTable entries={displayLeaderboard} />
            </section>

            {/* Latest Agent Decisions */}
            <section className="decisions-section">
                <h2><i className="fas fa-brain"></i> Latest Agent Decisions</h2>
                <DecisionFeed decisions={allDecisions} isLoading={decisionsLoading} />
            </section>

            {/* Equity Chart */}
            <section className="chart-section">
                <h2><i className="fas fa-chart-area"></i> Equity Race</h2>
                {equityLoading ? (
                    <div className="chart-loading">
                        <div className="spinner"></div>
                        <p>Loading equity curves...</p>
                    </div>
                ) : (
                    <EquityChart 
                        agents={displayEquity} 
                        height={450}
                        showLegend={true}
                    />
                )}
            </section>
        </div>
    );
}

interface DashboardStats {
    bestAgent: { name: string } | null;
    bestPerformance: number;
    totalAgents: number;
    activeAgents: number;
    totalValue: number;
    avgPerformance: number;
}

function calculateStats(leaderboard: LeaderboardEntry[]): DashboardStats {
    if (leaderboard.length === 0) {
        return {
            bestAgent: null,
            bestPerformance: 0,
            totalAgents: 0,
            activeAgents: 0,
            totalValue: 0,
            avgPerformance: 0,
        };
    }

    const sortedByPerformance = [...leaderboard].sort((a, b) => b.performancePercent - a.performancePercent);
    const bestEntry = sortedByPerformance[0];

    return {
        bestAgent: { name: bestEntry.agent.name },
        bestPerformance: bestEntry.performancePercent,
        totalAgents: leaderboard.length,
        activeAgents: leaderboard.filter(e => e.agent.isActive).length,
        totalValue: leaderboard.reduce((sum, e) => sum + e.currentValue, 0),
        avgPerformance: leaderboard.reduce((sum, e) => sum + e.performancePercent, 0) / leaderboard.length,
    };
}
