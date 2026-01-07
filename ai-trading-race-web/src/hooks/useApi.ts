import { useQuery } from '@tanstack/react-query';
import { agentsApi, equityApi, tradesApi } from '../services/api';

// Fetch all agents
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
