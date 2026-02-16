import axios from 'axios';
import type { AgentSummary, AgentDetail, EquitySnapshot, Trade, LeaderboardEntry, MarketPrice, Portfolio, DecisionLog } from '../types';

// Configure base URL for the .NET API
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001';

const apiClient = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    withCredentials: true,
});

// Agents API
export const agentsApi = {
    getAll: async (): Promise<AgentSummary[]> => {
        const response = await apiClient.get('/api/agents');
        return response.data;
    },

    getById: async (id: string): Promise<AgentDetail> => {
        const response = await apiClient.get(`/api/agents/${id}`);
        return response.data;
    },
};

// Equity API
export const equityApi = {
    getByAgentId: async (agentId: string): Promise<EquitySnapshot[]> => {
        const response = await apiClient.get(`/api/agents/${agentId}/equity`);
        return response.data;
    },

    getLeaderboard: async (): Promise<LeaderboardEntry[]> => {
        const response = await apiClient.get('/api/leaderboard');
        return response.data;
    },
};

// Trades API
export const tradesApi = {
    getByAgentId: async (agentId: string): Promise<Trade[]> => {
        const response = await apiClient.get(`/api/agents/${agentId}/trades`);
        // API returns { trades: [...], totalCount, limit, offset }
        return response.data.trades || [];
    },
};

// Market API
export const marketApi = {
    getAll: async (): Promise<MarketPrice[]> => {
        const response = await apiClient.get('/api/market/prices');
        return response.data;
    },

    getBySymbol: async (symbol: string): Promise<MarketPrice> => {
        const response = await apiClient.get(`/api/market/prices/${symbol}`);
        return response.data;
    },
};

// Portfolio API
export const portfolioApi = {
    getByAgentId: async (agentId: string): Promise<Portfolio> => {
        const response = await apiClient.get(`/api/agents/${agentId}/portfolio`);
        return response.data;
    },
};

// Decisions API
export const decisionsApi = {
    getByAgentId: async (agentId: string, limit: number = 50): Promise<DecisionLog[]> => {
        const response = await apiClient.get(`/api/agents/${agentId}/decisions`, {
            params: { limit },
        });
        return response.data;
    },
};

export { apiClient };
