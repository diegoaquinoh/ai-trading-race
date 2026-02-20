// API types matching the .NET domain models

// Agent summary from /api/agents endpoint
export interface AgentSummary {
  id: string;
  name: string;
  strategy: string;
  isActive: boolean;
  totalValue: number;
  percentChange: number;
  lastUpdated: string;
}

// Agent DTO from /api/leaderboard endpoint (nested in LeaderboardEntry)
export interface LeaderboardAgent {
  id: string;
  name: string;
  modelType: string;
  provider: string; // Note: this actually contains strategy text from backend
  isActive: boolean;
  createdAt: string;
}

// Full agent from /api/agents/:id endpoint
export interface AgentDetail {
  id: string;
  name: string;
  strategy: string;
  isActive: boolean;
  createdAt: string;
  latestSnapshot?: {
    id: string;
    portfolioId: string;
    agentId: string;
    capturedAt: string;
    totalValue: number;
    cashValue: number;
    positionsValue: number;
    unrealizedPnL: number;
    percentChange: number;
  };
  performance?: {
    agentId: string;
    initialValue: number;
    currentValue: number;
    totalReturn: number;
    percentReturn: number;
    maxDrawdown: number;
    sharpeRatio: number | null;
    totalTrades: number;
    winningTrades: number;
    losingTrades: number;
    winRate: number;
    calculatedAt: string;
  };
}

// Backwards compat alias
export type Agent = LeaderboardAgent;

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

export interface PortfolioPosition {
  assetSymbol: string;
  quantity: number;
  averagePrice: number;
  currentPrice: number;
}

export interface Portfolio {
  portfolioId: string;
  agentId: string;
  cash: number;
  positions: PortfolioPosition[];
  asOf: string;
  totalValue: number;
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
  agentId?: string;
  assetSymbol: string;
  side: 'Buy' | 'Sell';
  quantity: number;
  price: number;
  totalValue?: number;
  executedAt: string;
  rationale?: string | null;
  detectedRegime?: string | null;
}

export interface EquitySnapshot {
  id: string;
  portfolioId: string;
  agentId: string;
  capturedAt: string;  // Backend uses 'capturedAt' not 'timestamp'
  totalValue: number;
  cashValue: number;   // Backend uses 'cashValue' not 'cash'
  positionsValue: number;
  unrealizedPnL: number;
  percentChange: number | null;
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
  agent: LeaderboardAgent;
  currentValue: number;
  performancePercent: number;
  drawdown: number;
}

export interface DecisionLog {
  id: number;
  agentId: string;
  timestamp: string;
  action: string;
  asset: string | null;
  quantity: number | null;
  rationale: string;
  citedRuleIds: string;
  detectedRegime: string;
  portfolioValueBefore: number;
  portfolioValueAfter: number;
  wasValidated: boolean;
  validationErrors: string | null;
  createdAt: string;
}
