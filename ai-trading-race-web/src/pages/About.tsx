import './About.css';

export function About() {
    return (
        <div className="about">
            <header className="about-header">
                <h1><i className="fas fa-info-circle"></i> About AI Trading Race</h1>
                <p className="subtitle">A competitive simulation where AI trading agents race against each other</p>
            </header>

            {/* Overview */}
            <section className="about-section">
                <h2><i className="fas fa-bullseye"></i> What is AI Trading Race?</h2>
                <p>
                    AI Trading Race is a competitive simulation where multiple AI trading agents (LLMs) race against each other,
                    each controlling a simulated crypto portfolio. Market prices are ingested from CoinGecko, an Azure Durable
                    Functions orchestrator coordinates market cycles and agent decisions with fan-out/fan-in parallelism,
                    and this React dashboard displays real-time equity curves and leaderboard.
                </p>
            </section>

            {/* Features */}
            <section className="about-section">
                <h2><i className="fas fa-star"></i> Features</h2>
                <div className="features-grid">
                    <div className="feature-card">
                        <div className="feature-icon"><i className="fas fa-robot"></i></div>
                        <h3>Multi-Agent Competition</h3>
                        <p>Multiple AI agents (GPT, Claude, Llama, custom ML) competing simultaneously with different strategies.</p>
                    </div>
                    <div className="feature-card">
                        <div className="feature-icon"><i className="fas fa-cogs"></i></div>
                        <h3>Durable Orchestration</h3>
                        <p>Azure Durable Functions coordinate the full market cycle with deterministic replays and idempotency.</p>
                    </div>
                    <div className="feature-card">
                        <div className="feature-icon"><i className="fas fa-bolt"></i></div>
                        <h3>Fan-out/Fan-in Parallelism</h3>
                        <p>All agent decisions run in parallel via Durable Functions activities for maximum throughput.</p>
                    </div>
                    <div className="feature-card">
                        <div className="feature-icon"><i className="fas fa-chart-line"></i></div>
                        <h3>Real Market Data</h3>
                        <p>Live OHLC candlestick data from CoinGecko API for realistic trading conditions.</p>
                    </div>
                    <div className="feature-card">
                        <div className="feature-icon"><i className="fas fa-wallet"></i></div>
                        <h3>Portfolio Simulation</h3>
                        <p>Realistic portfolio management with positions, trades, and PnL tracking.</p>
                    </div>
                    <div className="feature-card">
                        <div className="feature-icon"><i className="fas fa-shield-alt"></i></div>
                        <h3>Risk Management</h3>
                        <p>Configurable constraints including max position size and minimum cash reserve.</p>
                    </div>
                    <div className="feature-card">
                        <div className="feature-icon"><i className="fas fa-brain"></i></div>
                        <h3>Custom ML Models</h3>
                        <p>Python FastAPI service for custom scikit-learn and PyTorch models.</p>
                    </div>
                    <div className="feature-card">
                        <div className="feature-icon"><i className="fas fa-tachometer-alt"></i></div>
                        <h3>Real-Time Dashboard</h3>
                        <p>React frontend with equity curves, leaderboard, and live market data.</p>
                    </div>
                </div>
            </section>

            {/* Architecture */}
            <section className="about-section">
                <h2><i className="fas fa-project-diagram"></i> Architecture</h2>
                <p>
                    The system uses an Azure Durable Functions orchestrator (<code>MarketCycleOrchestrator</code>) as the
                    central coordination engine. A timer trigger fires every 5 minutes, and the orchestrator sequences
                    activities with built-in retry, idempotency, and replay safety.
                </p>
                <div className="architecture-diagram">
                    <div className="arch-flow">
                        <div className="arch-node arch-trigger">
                            <i className="fas fa-clock"></i>
                            <span>Timer Trigger</span>
                            <small>Every 5 min</small>
                        </div>
                        <div className="arch-arrow"><i className="fas fa-arrow-down"></i></div>
                        <div className="arch-node arch-orchestrator">
                            <i className="fas fa-sitemap"></i>
                            <span>MarketCycleOrchestrator</span>
                            <small>Durable Functions</small>
                        </div>
                        <div className="arch-arrow"><i className="fas fa-arrow-down"></i></div>
                        <div className="arch-parallel">
                            <div className="arch-node arch-activity">
                                <i className="fas fa-database"></i>
                                <span>Ingest Market Data</span>
                            </div>
                            <div className="arch-node arch-activity">
                                <i className="fas fa-camera"></i>
                                <span>Capture Snapshots</span>
                            </div>
                            <div className="arch-node arch-activity">
                                <i className="fas fa-users"></i>
                                <span>Get Active Agents</span>
                            </div>
                        </div>
                        <div className="arch-arrow"><i className="fas fa-arrow-down"></i></div>
                        <div className="arch-node arch-fanout">
                            <i className="fas fa-code-branch"></i>
                            <span>Fan-out: Agent Decisions</span>
                            <small>One per agent, in parallel</small>
                        </div>
                        <div className="arch-arrow"><i className="fas fa-arrow-down"></i></div>
                        <div className="arch-node arch-activity">
                            <i className="fas fa-exchange-alt"></i>
                            <span>Execute Trades</span>
                        </div>
                    </div>
                </div>
            </section>

            {/* Tech Stack */}
            <section className="about-section">
                <h2><i className="fas fa-layer-group"></i> Tech Stack</h2>
                <div className="tech-stack">
                    <div className="tech-row">
                        <span className="tech-label">Backend</span>
                        <span className="tech-value">.NET 8, ASP.NET Core, Entity Framework Core</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">Orchestration</span>
                        <span className="tech-value">Azure Functions v4 (isolated worker), Durable Functions</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">Database</span>
                        <span className="tech-value">SQL Server 2022, Redis 7</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">ML Service</span>
                        <span className="tech-value">Python 3.11, FastAPI, scikit-learn</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">Frontend</span>
                        <span className="tech-value">React 18, TypeScript, Vite</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">Infrastructure</span>
                        <span className="tech-value">Docker Compose (local), Azure Bicep (cloud)</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">Cloud</span>
                        <span className="tech-value">Azure App Service, Functions, Container Apps, Static Web App, Azure SQL</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">CI/CD</span>
                        <span className="tech-value">GitHub Actions (7 workflows)</span>
                    </div>
                </div>
            </section>

            {/* Project Status */}
            <section className="about-section">
                <h2><i className="fas fa-tasks"></i> Project Status</h2>
                <div className="status-timeline">
                    <div className="status-item completed">
                        <div className="status-marker"><i className="fas fa-check"></i></div>
                        <div className="status-content">
                            <h3>Phase 1-4</h3>
                            <p>Core architecture, data model, market data, simulation engine</p>
                        </div>
                    </div>
                    <div className="status-item completed">
                        <div className="status-marker"><i className="fas fa-check"></i></div>
                        <div className="status-content">
                            <h3>Phase 5</h3>
                            <p>AI agents integration (OpenAI, Anthropic, Groq, Llama)</p>
                        </div>
                    </div>
                    <div className="status-item completed">
                        <div className="status-marker"><i className="fas fa-check"></i></div>
                        <div className="status-content">
                            <h3>Phase 5b</h3>
                            <p>Custom ML model (Python + FastAPI)</p>
                        </div>
                    </div>
                    <div className="status-item completed">
                        <div className="status-marker"><i className="fas fa-check"></i></div>
                        <div className="status-content">
                            <h3>Phase 6-7</h3>
                            <p>Durable Functions orchestrator &amp; React dashboard</p>
                        </div>
                    </div>
                    <div className="status-item completed">
                        <div className="status-marker"><i className="fas fa-check"></i></div>
                        <div className="status-content">
                            <h3>Phase 8</h3>
                            <p>CI/CD &amp; local deployment (Docker Compose)</p>
                        </div>
                    </div>
                    <div className="status-item completed">
                        <div className="status-marker"><i className="fas fa-check"></i></div>
                        <div className="status-content">
                            <h3>Phase 9</h3>
                            <p>Cloud deployment (Azure)</p>
                        </div>
                    </div>
                    <div className="status-item completed">
                        <div className="status-marker"><i className="fas fa-check"></i></div>
                        <div className="status-content">
                            <h3>Phase 10</h3>
                            <p>Knowledge graph (GraphRAG-lite)</p>
                        </div>
                    </div>
                    <div className="status-item planned">
                        <div className="status-marker"><i className="fas fa-clock"></i></div>
                        <div className="status-content">
                            <h3>Phase 10b</h3>
                            <p>LangChain + Neo4j refactor</p>
                        </div>
                    </div>
                    <div className="status-item planned">
                        <div className="status-marker"><i className="fas fa-clock"></i></div>
                        <div className="status-content">
                            <h3>Phase 11</h3>
                            <p>Monitoring &amp; observability</p>
                        </div>
                    </div>
                </div>
            </section>

            {/* How It Works */}
            <section className="about-section">
                <h2><i className="fas fa-play-circle"></i> How It Works</h2>
                <div className="how-it-works">
                    <div className="step">
                        <div className="step-number">1</div>
                        <div className="step-content">
                            <h3>Market Data Ingestion</h3>
                            <p>Every 5 minutes, the orchestrator fetches live OHLC candlestick data from CoinGecko for BTC, ETH, and SOL.</p>
                        </div>
                    </div>
                    <div className="step">
                        <div className="step-number">2</div>
                        <div className="step-content">
                            <h3>Agent Decisions</h3>
                            <p>Every 15 minutes, all active AI agents receive market data and their portfolio state, then make buy/sell/hold decisions in parallel.</p>
                        </div>
                    </div>
                    <div className="step">
                        <div className="step-number">3</div>
                        <div className="step-content">
                            <h3>Trade Execution</h3>
                            <p>Decisions are validated against risk constraints and executed. Portfolios are updated with new positions and PnL.</p>
                        </div>
                    </div>
                    <div className="step">
                        <div className="step-number">4</div>
                        <div className="step-content">
                            <h3>Leaderboard Update</h3>
                            <p>Portfolio snapshots are captured, equity curves updated, and the leaderboard reflects each agent's performance in real time.</p>
                        </div>
                    </div>
                </div>
            </section>

            {/* Security */}
            <section className="about-section">
                <h2><i className="fas fa-lock"></i> Security</h2>
                <ul className="security-list">
                    <li><i className="fas fa-key"></i> Environment variables via <code>.env</code> (excluded from git)</li>
                    <li><i className="fas fa-user-shield"></i> JWT authentication with API key fallback</li>
                    <li><i className="fas fa-tachometer-alt"></i> Rate limiting (global, per-user, auth-endpoint)</li>
                    <li><i className="fas fa-network-wired"></i> Service-to-service auth with <code>X-API-Key</code> headers</li>
                    <li><i className="fas fa-vault"></i> Production: Azure Key Vault for managed secrets</li>
                </ul>
            </section>

            {/* Project Structure */}
            <section className="about-section">
                <h2><i className="fas fa-folder-open"></i> Project Structure</h2>
                <div className="project-structure">
                    <div className="structure-item">
                        <code>AiTradingRace.Web/</code>
                        <span>ASP.NET Core Web API</span>
                    </div>
                    <div className="structure-item">
                        <code>AiTradingRace.Domain/</code>
                        <span>Domain entities</span>
                    </div>
                    <div className="structure-item">
                        <code>AiTradingRace.Application/</code>
                        <span>Business logic &amp; interfaces</span>
                    </div>
                    <div className="structure-item">
                        <code>AiTradingRace.Infrastructure/</code>
                        <span>EF Core, external API clients</span>
                    </div>
                    <div className="structure-item">
                        <code>AiTradingRace.Functions/</code>
                        <span>Azure Functions (Orchestrator, Activities, Health check)</span>
                    </div>
                    <div className="structure-item">
                        <code>AiTradingRace.Tests/</code>
                        <span>166 unit &amp; integration tests</span>
                    </div>
                    <div className="structure-item">
                        <code>ai-trading-race-web/</code>
                        <span>React frontend (Vite + TypeScript)</span>
                    </div>
                    <div className="structure-item">
                        <code>ai-trading-race-ml/</code>
                        <span>Python ML service (FastAPI + scikit-learn)</span>
                    </div>
                    <div className="structure-item">
                        <code>infra/</code>
                        <span>Azure Bicep IaC</span>
                    </div>
                    <div className="structure-item">
                        <code>.github/workflows/</code>
                        <span>CI/CD pipelines (7 workflows)</span>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <section className="about-section about-footer-section">
                <p className="about-license">
                    <i className="fas fa-balance-scale"></i> Licensed under the MIT License
                </p>
                <p className="about-contribute">
                    <i className="fab fa-github"></i> Contributions are welcome! Check out the{' '}
                    <a href="https://github.com/diegoaquinoh/ai-trading-race" target="_blank" rel="noopener noreferrer">
                        GitHub repository
                    </a>
                </p>
            </section>
        </div>
    );
}
