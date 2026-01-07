import { useParams, Link } from 'react-router-dom';
import { useAgent, useEquity, useTrades } from '../hooks/useApi';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export function AgentDetail() {
    const { id } = useParams<{ id: string }>();
    const { data: agent, isLoading: agentLoading } = useAgent(id!);
    const { data: equity, isLoading: equityLoading } = useEquity(id!);
    const { data: trades, isLoading: tradesLoading } = useTrades(id!);

    if (agentLoading || equityLoading) {
        return (
            <div className="loading">
                <div className="spinner"></div>
                <p>Loading agent details...</p>
            </div>
        );
    }

    if (!agent) {
        return (
            <div className="error">
                <p>Agent not found</p>
                <Link to="/">← Back to Dashboard</Link>
            </div>
        );
    }

    return (
        <div className="agent-detail">
            <nav className="breadcrumb">
                <Link to="/">Dashboard</Link> / <span>{agent.name}</span>
            </nav>

            <header className="agent-header">
                <h1>{agent.name}</h1>
                <span className={`badge ${agent.modelType.toLowerCase()}`}>
                    {agent.modelType}
                </span>
                <span className={`status ${agent.isActive ? 'active' : 'inactive'}`}>
                    {agent.isActive ? '● Active' : '○ Inactive'}
                </span>
            </header>

            <section className="agent-info">
                <div className="info-card">
                    <h3>Provider</h3>
                    <p>{agent.provider}</p>
                </div>
                <div className="info-card">
                    <h3>Created</h3>
                    <p>{new Date(agent.createdAt).toLocaleDateString()}</p>
                </div>
            </section>

            <section className="equity-section">
                <h2>📈 Equity Curve</h2>
                <div className="chart-container">
                    <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={equity}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="timestamp" tickFormatter={(t) => new Date(t).toLocaleDateString()} />
                            <YAxis />
                            <Tooltip
                                labelFormatter={(t) => new Date(t).toLocaleString()}
                                formatter={(value) => value != null ? [`$${Number(value).toLocaleString()}`, 'Value'] : ['', 'Value']}
                            />
                            <Line
                                type="monotone"
                                dataKey="totalValue"
                                stroke="#8884d8"
                                strokeWidth={2}
                                dot={false}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </section>

            <section className="trades-section">
                <h2>📋 Recent Trades</h2>
                {tradesLoading ? (
                    <p>Loading trades...</p>
                ) : (
                    <table className="trades-table">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Action</th>
                                <th>Asset</th>
                                <th>Quantity</th>
                                <th>Price</th>
                            </tr>
                        </thead>
                        <tbody>
                            {trades?.slice(0, 20).map((trade) => (
                                <tr key={trade.id}>
                                    <td>{new Date(trade.executedAt).toLocaleString()}</td>
                                    <td className={trade.action.toLowerCase()}>
                                        {trade.action}
                                    </td>
                                    <td>{trade.asset}</td>
                                    <td>{trade.quantity.toFixed(4)}</td>
                                    <td>${trade.price.toLocaleString()}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </section>
        </div>
    );
}
