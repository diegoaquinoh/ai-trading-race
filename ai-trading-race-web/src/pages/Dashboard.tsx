import { useState, useEffect } from 'react';
import { useLeaderboard, useMarketPrices, useAllAgentEquity } from '../hooks/useApi';
import { StatCard, LeaderboardTable, EquityChart, MarketPrices, RefreshIndicator, LoadingSpinner, ErrorMessage } from '../components';
import './Dashboard.css';

export function Dashboard() {
    const { data: leaderboard, isLoading, error, dataUpdatedAt, isFetching, refetch } = useLeaderboard();
    const { data: marketPrices, isLoading: pricesLoading } = useMarketPrices();
    const { data: equityData, isLoading: equityLoading } = useAllAgentEquity(leaderboard);
    
    const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
    const [secondsUntilRefresh, setSecondsUntilRefresh] = useState(30);

    // Track last update time
    useEffect(() => {
        if (dataUpdatedAt) {
            setLastUpdate(new Date(dataUpdatedAt));
            setSecondsUntilRefresh(30);
        }
    }, [dataUpdatedAt]);

    // Countdown timer
    useEffect(() => {
        const interval = setInterval(() => {
            setSecondsUntilRefresh(prev => Math.max(0, prev - 1));
        }, 1000);
        return () => clearInterval(interval);
    }, []);

    // Calculate stats from leaderboard
    const stats = calculateStats(leaderboard);

    if (isLoading) {
        return (
            <div className="dashboard-loading">
                <LoadingSpinner size="lg" message="Loading leaderboard..." />
            </div>
        );
    }

    if (error) {
        return (
            <ErrorMessage 
                title="Failed to load dashboard"
                message={error.message}
                retryAction={() => refetch()}
                backLink="/"
            />
        );
    }

    return (
        <div className="dashboard">
            <header className="dashboard-header">
                <h1>🏁 AI Trading Race</h1>
                <p className="subtitle">Watch AI agents compete in real-time crypto trading</p>
            </header>

            {/* Market Prices */}
            <section className="market-section">
                <h2>💰 Market Prices</h2>
                <MarketPrices prices={marketPrices ?? []} isLoading={pricesLoading} />
            </section>

            {/* Stats Cards */}
            <section className="stats-section">
                <div className="stats-grid">
                    <StatCard
                        icon="🏆"
                        title="Best Performer"
                        value={stats.bestAgent?.name ?? 'N/A'}
                        trend={stats.bestPerformance >= 0 ? 'up' : 'down'}
                        trendValue={`${stats.bestPerformance >= 0 ? '+' : ''}${stats.bestPerformance.toFixed(2)}%`}
                    />
                    <StatCard
                        icon="📊"
                        title="Total Agents"
                        value={stats.totalAgents}
                        subtitle={`${stats.activeAgents} active`}
                    />
                    <StatCard
                        icon="💵"
                        title="Total AUM"
                        value={`$${(stats.totalValue / 1000).toFixed(0)}k`}
                        subtitle="Assets under management"
                    />
                    <StatCard
                        icon="📈"
                        title="Avg Performance"
                        value={`${stats.avgPerformance >= 0 ? '+' : ''}${stats.avgPerformance.toFixed(2)}%`}
                        trend={stats.avgPerformance >= 0 ? 'up' : 'down'}
                    />
                </div>
            </section>

            {/* Leaderboard */}
            <section className="leaderboard-section">
                <div className="section-header">
                    <h2>📊 Leaderboard</h2>
                    <RefreshIndicator 
                        lastUpdate={lastUpdate} 
                        isRefreshing={isFetching} 
                        nextRefreshIn={secondsUntilRefresh}
                    />
                </div>
                <LeaderboardTable entries={leaderboard ?? []} />
            </section>

            {/* Equity Chart */}
            <section className="chart-section">
                <h2>📈 Equity Race</h2>
                {equityLoading ? (
                    <div className="chart-loading">
                        <div className="spinner"></div>
                        <p>Loading equity curves...</p>
                    </div>
                ) : (
                    <EquityChart 
                        agents={equityData} 
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

function calculateStats(leaderboard: ReturnType<typeof useLeaderboard>['data']): DashboardStats {
    if (!leaderboard || leaderboard.length === 0) {
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
