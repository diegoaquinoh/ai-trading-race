import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { EquitySnapshot } from '../types';
import './EquityChart.css';

// Agent colors for differentiation
const AGENT_COLORS = [
    '#6366f1', // Primary purple
    '#10b981', // Green
    '#f59e0b', // Orange
    '#ef4444', // Red
    '#8b5cf6', // Violet
    '#ec4899', // Pink
    '#06b6d4', // Cyan
    '#84cc16', // Lime
];

interface AgentEquityData {
    agentId: string;
    agentName: string;
    data: EquitySnapshot[];
}

interface EquityChartProps {
    agents: AgentEquityData[];
    height?: number;
    showLegend?: boolean;
    title?: string;
}

interface ChartDataPoint {
    timestamp: string;
    formattedTime: string;
    [key: string]: string | number;
}

export function EquityChart({ agents, height = 400, showLegend = true, title }: EquityChartProps) {
    // Combine all agent data into a single array for the chart
    const chartData = buildChartData(agents);

    if (chartData.length === 0) {
        return (
            <div className="equity-chart-container">
                {title && <h3 className="equity-chart-title">{title}</h3>}
                <div className="equity-chart-empty">
                    No equity data available
                </div>
            </div>
        );
    }

    return (
        <div className="equity-chart-container">
            {title && <h3 className="equity-chart-title">{title}</h3>}
            <div className="equity-chart-wrapper">
                <ResponsiveContainer width="100%" height={height}>
                    <LineChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                        <XAxis 
                            dataKey="formattedTime" 
                            stroke="var(--text-secondary)"
                            fontSize={12}
                            tickLine={false}
                        />
                        <YAxis 
                            stroke="var(--text-secondary)"
                            fontSize={12}
                            tickLine={false}
                            tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                        />
                        <Tooltip 
                            contentStyle={{
                                background: 'var(--bg-card)',
                                border: '1px solid var(--border)',
                                borderRadius: '0.5rem',
                                color: 'var(--text-primary)',
                            }}
                            labelStyle={{ color: 'var(--text-secondary)' }}
                            formatter={(value: number | undefined) => value !== undefined ? [`$${value.toLocaleString()}`, 'Value'] : ['', 'Value']}
                        />
                        {showLegend && (
                            <Legend 
                                wrapperStyle={{ paddingTop: '1rem' }}
                            />
                        )}
                        {agents.map((agent, index) => (
                            <Line
                                key={agent.agentId}
                                type="monotone"
                                dataKey={agent.agentId}
                                name={agent.agentName}
                                stroke={AGENT_COLORS[index % AGENT_COLORS.length]}
                                strokeWidth={2}
                                dot={false}
                                activeDot={{ r: 5, strokeWidth: 2 }}
                                connectNulls
                            />
                        ))}
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}

function buildChartData(agents: AgentEquityData[]): ChartDataPoint[] {
    // Collect all unique timestamps and sort them
    const allTimestamps = new Map<number, string>(); // ms -> original string
    agents.forEach(agent => {
        agent.data.forEach(snapshot => {
            const ms = new Date(snapshot.capturedAt).getTime();
            if (!isNaN(ms)) {
                allTimestamps.set(ms, snapshot.capturedAt);
            }
        });
    });

    // Sort by timestamp
    const sortedMs = Array.from(allTimestamps.keys()).sort((a, b) => a - b);
    
    if (sortedMs.length === 0) {
        return [];
    }

    // For each agent, create a lookup by timestamp and also track last known value
    const agentDataLookup = new Map<string, Map<number, number>>();
    agents.forEach(agent => {
        const lookup = new Map<number, number>();
        agent.data.forEach(snapshot => {
            const ms = new Date(snapshot.capturedAt).getTime();
            if (!isNaN(ms)) {
                lookup.set(ms, snapshot.totalValue);
            }
        });
        agentDataLookup.set(agent.agentId, lookup);
    });

    // Build data points with forward-filling (carry last known value forward)
    const lastValues = new Map<string, number>();
    const dataPoints: ChartDataPoint[] = sortedMs.map(ms => {
        const timestamp = allTimestamps.get(ms)!;
        const point: ChartDataPoint = {
            timestamp,
            formattedTime: formatTimestamp(timestamp, sortedMs),
        };

        agents.forEach(agent => {
            const lookup = agentDataLookup.get(agent.agentId);
            if (lookup?.has(ms)) {
                const value = lookup.get(ms)!;
                point[agent.agentId] = value;
                lastValues.set(agent.agentId, value);
            } else if (lastValues.has(agent.agentId)) {
                // Forward-fill with last known value
                point[agent.agentId] = lastValues.get(agent.agentId)!;
            }
        });

        return point;
    });

    return dataPoints;
}

function formatTimestamp(timestamp: string, allTimestamps?: number[]): string {
    if (!timestamp) return '';
    
    const date = new Date(timestamp);
    
    // Check if date is valid
    if (isNaN(date.getTime())) {
        return timestamp.slice(0, 10);
    }
    
    // Determine if we need to show seconds based on time span
    const showSeconds = allTimestamps && allTimestamps.length > 1 && 
        (allTimestamps[allTimestamps.length - 1] - allTimestamps[0]) < 60 * 60 * 1000; // Less than 1 hour span
    
    if (showSeconds) {
        return date.toLocaleTimeString('en-US', { 
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }
    
    return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

