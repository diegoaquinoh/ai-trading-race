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
                            />
                        ))}
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}

function buildChartData(agents: AgentEquityData[]): ChartDataPoint[] {
    // Collect all unique timestamps
    const timestampSet = new Set<string>();
    agents.forEach(agent => {
        agent.data.forEach(snapshot => {
            timestampSet.add(snapshot.timestamp);
        });
    });

    // Sort timestamps
    const sortedTimestamps = Array.from(timestampSet).sort();

    // Build data points
    const dataPoints: ChartDataPoint[] = sortedTimestamps.map(timestamp => {
        const point: ChartDataPoint = {
            timestamp,
            formattedTime: formatTimestamp(timestamp),
        };

        agents.forEach(agent => {
            const snapshot = agent.data.find(s => s.timestamp === timestamp);
            if (snapshot) {
                point[agent.agentId] = snapshot.totalValue;
            }
        });

        return point;
    });

    return dataPoints;
}

function formatTimestamp(timestamp: string): string {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}
