import { useQuery, useQueries } from '@tanstack/react-query';
import { agentsApi, equityApi, tradesApi, marketApi } from '../services/api';
import type { LeaderboardEntry } from '../types';

// Fetch all agents (returns AgentSummary array)
export function useAgents() {
    return useQuery({
        queryKey: ['agents'],
        queryFn: agentsApi.getAll,
    });
}

// Fetch single agent by ID
export function useAgent(id: string) {
    return useQuery({
        queryKey: ['agent', id],
        queryFn: () => agentsApi.getById(id),
        enabled: !!id,
    });
}

// Fetch equity history for an agent
export function useEquity(agentId: string) {
    return useQuery({
        queryKey: ['equity', agentId],
        queryFn: () => equityApi.getByAgentId(agentId),
        enabled: !!agentId,
    });
}

// Fetch leaderboard
export function useLeaderboard() {
    return useQuery({
        queryKey: ['leaderboard'],
        queryFn: equityApi.getLeaderboard,
        refetchInterval: 30000, // Refresh every 30 seconds
    });
}

// Fetch trades for an agent
export function useTrades(agentId: string) {
    return useQuery({
        queryKey: ['trades', agentId],
        queryFn: () => tradesApi.getByAgentId(agentId),
        enabled: !!agentId,
    });
}

// Fetch market prices
export function useMarketPrices() {
    return useQuery({
        queryKey: ['marketPrices'],
        queryFn: marketApi.getAll,
        refetchInterval: 60000, // Refresh every 60 seconds
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
