// API types matching the .NET domain models

export interface Agent {
  id: string;
  name: string;
  modelType: string;
  provider: string;
  isActive: boolean;
  createdAt: string;
}

export interface MarketPrice {
  symbol: string;
  name: string;
  price: number;
  change24h: number;
  changePercent24h: number;
  high24h: number;
  low24h: number;
  updatedAt: string;
}

export interface Position {
  id: string;
  agentId: string;
  asset: string;
  quantity: number;
  averagePrice: number;
}

export interface Trade {
  id: string;
  agentId: string;
  asset: string;
  action: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  executedAt: string;
}

export interface EquitySnapshot {
  id: string;
  agentId: string;
  totalValue: number;
  cash: number;
  timestamp: string;
}

export interface MarketCandle {
  asset: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LeaderboardEntry {
  agent: Agent;
  currentValue: number;
  performancePercent: number;
  drawdown: number;
}
