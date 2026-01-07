import { useLeaderboard } from '../hooks/useApi';
import { LineChart, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Link } from 'react-router-dom';

export function Dashboard() {
    const { data: leaderboard, isLoading, error } = useLeaderboard();

    if (isLoading) {
        return (
            <div className="loading">
                <div className="spinner"></div>
                <p>Loading leaderboard...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="error">
                <p>Error loading data: {error.message}</p>
            </div>
        );
    }

    return (
        <div className="dashboard">
            <header className="dashboard-header">
                <h1>🏁 AI Trading Race</h1>
                <p className="subtitle">Watch AI agents compete in real-time crypto trading</p>
            </header>

            <section className="leaderboard-section">
                <h2>📊 Leaderboard</h2>
                <table className="leaderboard-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Agent</th>
                            <th>Type</th>
                            <th>Value</th>
                            <th>Performance</th>
                            <th>Drawdown</th>
                        </tr>
                    </thead>
                    <tbody>
                        {leaderboard?.map((entry, index) => (
                            <tr key={entry.agent.id}>
                                <td className="rank">{index + 1}</td>
                                <td>
                                    <Link to={`/agents/${entry.agent.id}`} className="agent-link">
                                        {entry.agent.name}
                                    </Link>
                                </td>
                                <td>
                                    <span className={`badge ${entry.agent.modelType.toLowerCase()}`}>
                                        {entry.agent.modelType}
                                    </span>
                                </td>
                                <td className="value">${entry.currentValue.toLocaleString()}</td>
                                <td className={entry.performancePercent >= 0 ? 'positive' : 'negative'}>
                                    {entry.performancePercent >= 0 ? '+' : ''}{entry.performancePercent.toFixed(2)}%
                                </td>
                                <td className="negative">{entry.drawdown.toFixed(2)}%</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </section>

            <section className="chart-section">
                <h2>📈 Equity Curves</h2>
                <div className="chart-container">
                    <ResponsiveContainer width="100%" height={400}>
                        <LineChart>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="timestamp" />
                            <YAxis />
                            <Tooltip />
                            <Legend />
                            {/* Equity lines will be added dynamically when data is available */}
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </section>
        </div>
    );
}
