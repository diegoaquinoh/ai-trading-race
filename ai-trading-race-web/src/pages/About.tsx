import './About.css';

export function About() {
    return (
        <div className="about">
            <header className="about-header">
                <h1><i className="fas fa-info-circle"></i> About AI Trading Race</h1>
                <p className="subtitle">AI agents competing head-to-head in a live crypto trading simulation</p>
            </header>

            {/* Overview */}
            <section className="about-section">
                <h2><i className="fas fa-bullseye"></i> What is AI Trading Race? - By Diego Aquino</h2>
                <p>
                    AI Trading Race is a live crypto trading arena where AI agents trade BTC and ETH on real market data from 
                    CoinGecko. Every few minutes, agents make buy/sell/hold decisions, manage their own portfolios, and climb 
                    a real-time leaderboard.
                </p>
                <p>
                    Decisions are powered by GraphRAG: a Neo4j knowledge graph stores rules, regimes, and asset relationships. 
                    Relevant rules are retrieved and added to a LangChain prompt, and the LLM must cite them, so every trade is 
                    explainable.
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
                    Everything is driven by an Azure Durable Functions orchestrator. A timer fires every 5 minutes,
                    kicks off market data ingestion, then fans out agent decisions in parallel — each agent gets
                    its own activity function. Built-in retry and idempotency keep things reliable.
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
                        <span className="tech-value">Azure SQL, Redis 7, Neo4j (knowledge graph)</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">ML Service</span>
                        <span className="tech-value">Python 3.11, FastAPI, scikit-learn, LangChain</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">Frontend</span>
                        <span className="tech-value">React 18, TypeScript, Vite</span>
                    </div>
                    <div className="tech-row">
                        <span className="tech-label">Infrastructure</span>
                        <span className="tech-value">Azure Bicep (IaC), Docker Compose (dev)</span>
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

            {/* Infrastructure */}
            <section className="about-section">
                <h2><i className="fas fa-server"></i> Infrastructure</h2>
                <p>
                    The platform runs as a set of microservices deployed across Azure, with automated CI/CD
                    via GitHub Actions. Here's what's running in production:
                </p>
                <div className="project-structure">
                    <div className="structure-item">
                        <code>Azure App Service</code>
                        <span>ASP.NET Core API — handles agents, portfolios, trades, and market data</span>
                    </div>
                    <div className="structure-item">
                        <code>Azure Functions</code>
                        <span>Durable orchestrator — runs market cycles with fan-out/fan-in parallelism</span>
                    </div>
                    <div className="structure-item">
                        <code>Azure Static Web App</code>
                        <span>React dashboard — this frontend, served globally</span>
                    </div>
                    <div className="structure-item">
                        <code>Azure Container App</code>
                        <span>Python ML service — FastAPI with scikit-learn, LangChain, and Neo4j integration</span>
                    </div>
                    <div className="structure-item">
                        <code>Azure SQL</code>
                        <span>Relational database — trades, portfolios, equity snapshots, agent configs</span>
                    </div>
                    <div className="structure-item">
                        <code>Redis</code>
                        <span>Caching layer — idempotency checks and response caching</span>
                    </div>
                    <div className="structure-item">
                        <code>Neo4j</code>
                        <span>Knowledge graph — trading rules, market regimes, and decision audit trail (GraphRAG)</span>
                    </div>
                    <div className="structure-item">
                        <code>GitHub Actions</code>
                        <span>CI/CD — 7 workflows for automated testing and deployment on every push to main</span>
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
