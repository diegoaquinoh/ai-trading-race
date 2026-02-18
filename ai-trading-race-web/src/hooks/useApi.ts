import { useQuery, useQueries } from '@tanstack/react-query';
import { agentsApi, equityApi, tradesApi, marketApi, portfolioApi, decisionsApi } from '../services/api';
import type { AgentSummary, AgentDetail, LeaderboardEntry, MarketPrice, Portfolio, Trade, DecisionLog, EquitySnapshot } from '../types';

// ═══════════════════════════════════════════════════════════════════════
//  PLACEHOLDER DATA — rendered when the backend is unreachable
// ═══════════════════════════════════════════════════════════════════════

const PLACEHOLDER_AGENTS: AgentSummary[] = [
    { id: 'placeholder-1', name: 'Agent Alpha', strategy: 'Momentum Strategy', isActive: true, totalValue: 100000, percentChange: 0, lastUpdated: new Date().toISOString() },
    { id: 'placeholder-2', name: 'Agent Beta', strategy: 'Mean Reversion', isActive: true, totalValue: 100000, percentChange: 0, lastUpdated: new Date().toISOString() },
    { id: 'placeholder-3', name: 'Agent Gamma', strategy: 'ML Ensemble', isActive: false, totalValue: 100000, percentChange: 0, lastUpdated: new Date().toISOString() },
];

const PLACEHOLDER_LEADERBOARD: LeaderboardEntry[] = PLACEHOLDER_AGENTS.map(a => ({
    agent: { id: a.id, name: a.name, modelType: 'Mock', provider: a.strategy, isActive: a.isActive, createdAt: a.lastUpdated },
    currentValue: 100000,
    performancePercent: 0,
    drawdown: 0,
}));

const PLACEHOLDER_MARKET_PRICES: MarketPrice[] = [
    { symbol: 'BTC', name: 'Bitcoin', price: 0, change24h: 0, changePercent24h: 0, high24h: 0, low24h: 0, updatedAt: new Date().toISOString() },
    { symbol: 'ETH', name: 'Ethereum', price: 0, change24h: 0, changePercent24h: 0, high24h: 0, low24h: 0, updatedAt: new Date().toISOString() },
    { symbol: 'SOL', name: 'Solana', price: 0, change24h: 0, changePercent24h: 0, high24h: 0, low24h: 0, updatedAt: new Date().toISOString() },
];

const PLACEHOLDER_AGENT_DETAIL: AgentDetail = {
    id: 'placeholder-1',
    name: 'Agent (offline)',
    strategy: '—',
    isActive: false,
    createdAt: new Date().toISOString(),
};

const PLACEHOLDER_PORTFOLIO: Portfolio = {
    portfolioId: 'placeholder',
    agentId: 'placeholder-1',
    cash: 100000,
    positions: [],
    asOf: new Date().toISOString(),
    totalValue: 100000,
};

// ═══════════════════════════════════════════════════════════════════════
//  HOOKS
// ═══════════════════════════════════════════════════════════════════════

// Fetch all agents (returns AgentSummary array)
export function useAgents() {
    return useQuery({
        queryKey: ['agents'],
        queryFn: agentsApi.getAll,
        placeholderData: PLACEHOLDER_AGENTS,
    });
}

// Fetch single agent by ID
export function useAgent(id: string) {
    return useQuery({
        queryKey: ['agent', id],
        queryFn: () => agentsApi.getById(id),
        enabled: !!id,
        placeholderData: PLACEHOLDER_AGENT_DETAIL,
    });
}

// Fetch equity history for an agent
export function useEquity(agentId: string) {
    return useQuery({
        queryKey: ['equity', agentId],
        queryFn: () => equityApi.getByAgentId(agentId),
        enabled: !!agentId,
        placeholderData: [] as EquitySnapshot[],
    });
}

// Fetch leaderboard
export function useLeaderboard() {
    return useQuery({
        queryKey: ['leaderboard'],
        queryFn: equityApi.getLeaderboard,
        refetchInterval: 30000,
        placeholderData: PLACEHOLDER_LEADERBOARD,
    });
}

// Fetch trades for an agent
export function useTrades(agentId: string) {
    return useQuery({
        queryKey: ['trades', agentId],
        queryFn: () => tradesApi.getByAgentId(agentId),
        enabled: !!agentId,
        placeholderData: [] as Trade[],
    });
}

// Fetch portfolio for an agent
export function usePortfolio(agentId: string) {
    return useQuery({
        queryKey: ['portfolio', agentId],
        queryFn: () => portfolioApi.getByAgentId(agentId),
        enabled: !!agentId,
        placeholderData: PLACEHOLDER_PORTFOLIO,
    });
}

// Fetch market prices
export function useMarketPrices() {
    return useQuery({
        queryKey: ['marketPrices'],
        queryFn: marketApi.getAll,
        refetchInterval: 60000,
        placeholderData: PLACEHOLDER_MARKET_PRICES,
    });
}

// Fetch decision logs for an agent
export function useDecisions(agentId: string) {
    return useQuery({
        queryKey: ['decisions', agentId],
        queryFn: () => decisionsApi.getByAgentId(agentId),
        enabled: !!agentId,
        placeholderData: [] as DecisionLog[],
    });
}

// Fetch equity for all agents (for multi-agent chart)
export function useAllAgentEquity(leaderboard: LeaderboardEntry[] | undefined) {
    const queries = useQueries({
        queries: (leaderboard ?? []).map(entry => ({
            queryKey: ['equity', entry.agent.id],
            queryFn: () => equityApi.getByAgentId(entry.agent.id),
            enabled: !!entry.agent.id,
            staleTime: 30000,
        })),
    });

    const isLoading = queries.some(q => q.isLoading);
    const data = queries.map((q, i) => ({
        agentId: leaderboard?.[i]?.agent.id ?? '',
        agentName: leaderboard?.[i]?.agent.name ?? '',
        data: q.data ?? [],
    })).filter(d => d.data.length > 0);

    return { data, isLoading };
}
