# Phase 10b — LangChain + Neo4j: GraphRAG for Explainable Trading Decisions

**Objective:** Replace the in-memory knowledge graph with Neo4j and introduce LangChain for structured LLM reasoning, enabling true graph-based retrieval-augmented generation (GraphRAG) for agent decisions.

**Status:** 📝 PLANNED  
**Priority:** 🟡 MEDIUM  
**Estimated Effort:** 3–4 weeks (6 sprints)  
**Date:** February 8, 2026  
**Branch:** `feature/langchain-neo4j`  
**Prerequisites:** Phase 10 domain model (already merged — `RuleNode`, `RegimeNode`, `RuleEdge`, `IKnowledgeGraphService`)

---

## 📋 Executive Summary

This plan upgrades the GraphRAG-lite system (Phase 10) from an in-memory, hard-coded knowledge graph to a production-grade stack:

| Layer | Current (Phase 10) | Target (Phase 10b) |
|-------|--------------------|--------------------|
| **Knowledge Graph** | `InMemoryKnowledgeGraphService` — C# `List<T>` | **Neo4j Community** — native graph DB |
| **LLM Integration** | Direct Azure OpenAI SDK calls with string prompts | **LangChain** — structured chains, output parsing, memory |
| **Graph Queries** | LINQ filtering on flat lists | **Cypher** — traversals, pattern matching, subgraph extraction |
| **Audit Trail** | SQL Server flat table | SQL Server + **Neo4j decision nodes** linked to rules |
| **Prompt Engineering** | Manual string concatenation in C# | **LangChain PromptTemplates** + `PydanticOutputParser` |

### Cost Impact

| Component | License | Monthly Cost |
|-----------|---------|-------------|
| Neo4j Community Edition | GPLv3 (open source) | **$0** |
| LangChain | MIT (open source) | **$0** |
| `langchain-openai` | MIT | **$0** |
| `neo4j` Python driver | Apache 2.0 | **$0** |
| Azure OpenAI API calls | Pay-per-use | **Already budgeted** (no change) |
| **Total added infrastructure cost** | | **$0/month** |

---

## 🏗️ Architecture: Before & After

### Current Architecture (Phase 8)

```
┌──────────────┐    HTTP/REST    ┌─────────────────────────┐
│  C# Backend  │ ──────────────► │  Python ML Service      │
│  (AgentRunner)│                 │  (FastAPI + sklearn)    │
│              │ ◄────────────── │  decision_service.py    │
│              │                 │                          │
│  AzureOpenAi │ ──── SDK ────► │  Azure OpenAI API        │
│  AgentClient │ ◄──────────── │                          │
└──────┬───────┘                └─────────────────────────┘
       │
       ▼
  ┌──────────┐   ┌───────┐
  │ SQL Server│   │ Redis │
  └──────────┘   └───────┘
```

### Target Architecture (Phase 10b)

```
┌──────────────┐    HTTP/REST    ┌──────────────────────────────────┐
│  C# Backend  │ ──────────────► │  Python ML Service (FastAPI)     │
│  (AgentRunner)│                 │                                  │
│              │ ◄────────────── │  ┌────────────────────────────┐  │
│              │                 │  │  LangChain                  │  │
│              │                 │  │  ├── AzureChatOpenAI        │  │
│              │                 │  │  ├── PromptTemplate         │  │
│              │                 │  │  ├── PydanticOutputParser   │  │
│              │                 │  │  └── Neo4jGraphQA (opt.)    │  │
│              │                 │  └────────────────────────────┘  │
│              │                 │                  │                │
│              │                 │                  ▼                │
│              │                 │  ┌────────────────────────────┐  │
│              │                 │  │  Neo4j Python Driver       │  │
│              │                 │  │  ├── Read: subgraph query  │  │
│              │                 │  │  └── Write: decision audit │  │
│              │                 │  └────────────┬───────────────┘  │
└──────┬───────┘                └────────────────┼─────────────────┘
       │                                         │
       ▼                                         ▼
  ┌──────────┐   ┌───────┐              ┌──────────────┐
  │ SQL Server│   │ Redis │              │  Neo4j       │
  │ (trades,  │   │       │              │  (rules,     │
  │  equity,  │   │       │              │   regimes,   │
  │  agents)  │   │       │              │   decisions) │
  └──────────┘   └───────┘              └──────────────┘
```

### Data Ownership Split

| Data | Storage | Rationale |
|------|---------|-----------|
| Agents, Portfolios, Trades, Equity | **SQL Server** | Transactional, relational, existing schema |
| Market Candles (OHLCV) | **SQL Server** | Time-series, batch queries |
| Rules, Regimes, Edges | **Neo4j** | Graph traversals, relationship queries |
| Decision Audit Nodes | **Neo4j** | Link decisions → rules cited |
| Decision summary (flat) | **SQL Server** | `AgentDecisions` table (existing) |
| Redis Idempotency | **Redis** | TTL cache, unchanged |

---

## 📦 Sprint Breakdown

### Sprint 10b.1 — Neo4j Infrastructure Setup (2–3 days)

**Goal:** Neo4j running in Docker Compose with seed data, accessible from Python.

**Tasks:**

1. **Add Neo4j to `docker-compose.yml`:**
   ```yaml
   neo4j:
     image: neo4j:5-community
     container_name: ai-trading-neo4j
     ports:
       - "7474:7474"   # Browser UI
       - "7687:7687"   # Bolt protocol
     environment:
       - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD:-tradingrace2026}
       - NEO4J_PLUGINS=["apoc"]
       - NEO4J_dbms_memory_heap_initial__size=256m
       - NEO4J_dbms_memory_heap_max__size=512m
     volumes:
       - neo4j-data:/data
       - neo4j-logs:/logs
     healthcheck:
       test: ["CMD-SHELL", "cypher-shell -u neo4j -p $$NEO4J_AUTH_PASSWORD 'RETURN 1'"]
       interval: 10s
       timeout: 5s
       retries: 5
       start_period: 30s
     restart: unless-stopped
     networks:
       - ai-trading-network
   ```

2. **Create seed script `scripts/seed-neo4j.sh`:**
   - Waits for Neo4j health check.
   - Runs Cypher statements to create:
     - 5 Rule nodes (R001–R005) with properties.
     - 4 Regime nodes (VOLATILE, BULLISH, BEARISH, STABLE).
     - 2 Asset nodes (BTC, ETH).
     - 6+ edges (ACTIVATES, RELAXES, TIGHTENS, SUBJECT_TO).
   - Idempotent (`MERGE` instead of `CREATE`).

3. **Cypher seed data:**
   ```cypher
   // Rules
   MERGE (r:Rule {id: 'R001'})
   SET r.name = 'MaxPositionSize',
       r.description = 'No single position should exceed 50% of total portfolio value',
       r.category = 'RiskManagement',
       r.severity = 'High',
       r.threshold = 0.5,
       r.unit = 'percentage',
       r.isActive = true;

   // (repeat for R002–R005)

   // Regimes
   MERGE (reg:Regime {id: 'VOLATILE'})
   SET reg.name = 'Volatile Market',
       reg.description = 'Daily volatility > 5%',
       reg.condition = 'volatility_7d > 0.05',
       reg.lookbackDays = 7;

   // (repeat for BULLISH, BEARISH, STABLE)

   // Assets
   MERGE (a:Asset {symbol: 'BTC'}) SET a.name = 'Bitcoin';
   MERGE (a:Asset {symbol: 'ETH'}) SET a.name = 'Ethereum';

   // Edges
   MATCH (reg:Regime {id: 'VOLATILE'}), (r:Rule {id: 'R003'})
   MERGE (reg)-[:ACTIVATES]->(r);

   MATCH (reg:Regime {id: 'VOLATILE'}), (r:Rule {id: 'R002'})
   MERGE (reg)-[:TIGHTENS {threshold: 200.0}]->(r);

   MATCH (reg:Regime {id: 'BULLISH'}), (r:Rule {id: 'R001'})
   MERGE (reg)-[:RELAXES {threshold: 0.6}]->(r);

   MATCH (reg:Regime {id: 'BEARISH'}), (r:Rule {id: 'R001'})
   MERGE (reg)-[:TIGHTENS {threshold: 0.3}]->(r);

   MATCH (a:Asset {symbol: 'BTC'}), (r:Rule {id: 'R001'})
   MERGE (a)-[:SUBJECT_TO]->(r);

   MATCH (a:Asset {symbol: 'ETH'}), (r:Rule {id: 'R001'})
   MERGE (a)-[:SUBJECT_TO]->(r);
   ```

4. **Update `.env.example` files** with `NEO4J_PASSWORD`, `NEO4J_URI`.

5. **Update `DEPLOYMENT_LOCAL.md`** with Neo4j startup instructions.

**Exit Criteria:**
- `docker compose up -d neo4j` starts successfully.
- Neo4j Browser at `http://localhost:7474` shows the seeded graph.
- Health check passes in `docker compose ps`.

---

### Sprint 10b.2 — LangChain + Neo4j Python Layer (3–4 days)

**Goal:** Python service can query Neo4j for rule subgraphs and use LangChain for structured LLM calls.

**Tasks:**

1. **Add dependencies to `requirements.txt`:**
   ```
   # LangChain core
   langchain>=0.3.0
   langchain-openai>=0.2.0
   langchain-community>=0.3.0

   # Neo4j
   neo4j>=5.20.0
   ```

2. **Create `app/graph/neo4j_client.py` — Neo4j connection manager:**
   ```python
   class Neo4jClient:
       """Manages Neo4j driver lifecycle and provides query methods."""

       def __init__(self, uri: str, user: str, password: str):
           self._driver = GraphDatabase.driver(uri, auth=(user, password))

       async def get_subgraph(self, regime_id: str, asset_symbols: list[str]) -> dict:
           """Extract relevant rules for a given regime and assets."""

       async def get_all_rules(self) -> list[dict]:
           """Return all active rules."""

       async def record_decision(self, decision_node: dict) -> None:
           """Write a Decision node linked to cited rules."""

       def close(self):
           self._driver.close()
   ```

3. **Create `app/graph/queries.py` — Cypher query constants:**
   ```python
   GET_SUBGRAPH = """
   MATCH (reg:Regime {id: $regime_id})-[edge]->(rule:Rule)
   WHERE rule.isActive = true
   RETURN rule, type(edge) AS relationship, properties(edge) AS params
   UNION
   MATCH (rule:Rule)
   WHERE rule.isActive = true AND rule.severity = 'Critical'
   RETURN rule, 'ALWAYS_ACTIVE' AS relationship, {} AS params
   """

   GET_ASSET_RULES = """
   MATCH (a:Asset)-[edge:SUBJECT_TO]->(rule:Rule)
   WHERE a.symbol IN $symbols AND rule.isActive = true
   RETURN a.symbol AS asset, rule, type(edge) AS relationship
   """

   RECORD_DECISION = """
   CREATE (d:Decision {
       agentId: $agent_id,
       timestamp: datetime($timestamp),
       action: $action,
       asset: $asset,
       quantity: $quantity,
       regime: $regime,
       reasoning: $reasoning
   })
   WITH d
   UNWIND $cited_rules AS ruleId
   MATCH (r:Rule {id: ruleId})
   CREATE (d)-[:CITED]->(r)
   """
   ```

4. **Create `app/chains/trading_chain.py` — LangChain chain for trading decisions:**
   ```python
   from langchain_openai import AzureChatOpenAI
   from langchain.prompts import ChatPromptTemplate
   from langchain.output_parsers import PydanticOutputParser

   class TradingDecisionChain:
       """LangChain-based trading decision pipeline."""

       def __init__(self, neo4j_client, azure_config):
           self.neo4j = neo4j_client
           self.llm = AzureChatOpenAI(
               azure_endpoint=azure_config.endpoint,
               azure_deployment=azure_config.deployment,
               api_version=azure_config.api_version,
               api_key=azure_config.api_key,
               temperature=0.7,
               max_tokens=1000,
           )
           self.parser = PydanticOutputParser(
               pydantic_object=LangChainDecisionResponse
           )

       async def run(self, context: AgentContextRequest) -> AgentDecisionResponse:
           # 1. Detect regime (reuse existing VolatilityBasedRegimeDetector logic)
           # 2. Query Neo4j for applicable rules
           # 3. Build structured prompt with LangChain template
           # 4. Call Azure OpenAI via LangChain
           # 5. Parse & validate response
           # 6. Record decision in Neo4j audit trail
           pass
   ```

5. **Create `app/chains/prompts.py` — Centralized prompt templates:**
   ```python
   TRADING_SYSTEM_PROMPT = ChatPromptTemplate.from_messages([
       ("system", """You are an AI trading agent managing a crypto portfolio.

   ## ACTIVE RULES (Knowledge Graph)
   You MUST cite rule IDs from this list when justifying your decision:
   {rules_context}

   ## CURRENT MARKET REGIME: {regime}
   Regime-specific modifications:
   {regime_modifications}

   ## OUTPUT FORMAT
   {format_instructions}

   IMPORTANT: Every order MUST include at least one cited_rule from the active rules above.
   """),
       ("user", """## PORTFOLIO STATE
   Cash: ${cash}
   Positions: {positions}
   Total Value: ${total_value}

   ## RECENT MARKET DATA (last {candle_count} candles)
   {market_data}

   ## AGENT INSTRUCTIONS
   {instructions}

   Analyze the data and make your trading decision:"""),
   ])
   ```

6. **Create `app/models/langchain_schemas.py` — Pydantic models for LangChain parser:**
   ```python
   class CitedOrder(BaseModel):
       action: Literal["BUY", "SELL", "HOLD"]
       asset: str
       quantity: Decimal
       rationale: str
       cited_rules: list[str] = Field(
           description="Rule IDs from the knowledge graph (e.g., R001, R003)"
       )

   class LangChainDecisionResponse(BaseModel):
       orders: list[CitedOrder]
       reasoning: str
       detected_regime: str
       confidence: float = Field(ge=0.0, le=1.0)
   ```

**Exit Criteria:**
- `Neo4jClient` connects and queries the graph successfully.
- `TradingDecisionChain.run()` returns a valid `AgentDecisionResponse`.
- Unit tests pass for Cypher queries (with test container or mock).

---

### Sprint 10b.3 — FastAPI Integration & New Endpoint (2–3 days)

**Goal:** Expose LangChain-based decisions via the existing ML service API.

**Tasks:**

1. **Add new endpoint `POST /decide` to `main.py`:**
   ```python
   @app.post("/decide", response_model=AgentDecisionResponse)
   async def langchain_decide(context: AgentContextRequest):
       """Generate a trading decision using LangChain + Neo4j GraphRAG."""
       return await trading_chain.run(context)
   ```
   - Keep existing `POST /predict` endpoint unchanged (sklearn model).
   - New `/decide` endpoint uses LangChain + Neo4j.
   - Both coexist — agents choose which endpoint based on `ModelProvider`.

2. **Update `app/config.py` — Add Neo4j and Azure OpenAI settings:**
   ```python
   # Neo4j
   neo4j_uri: str = "bolt://localhost:7687"
   neo4j_user: str = "neo4j"
   neo4j_password: str = ""

   # Azure OpenAI (for LangChain)
   azure_openai_endpoint: str = ""
   azure_openai_api_key: str = ""
   azure_openai_deployment: str = "gpt-4"
   azure_openai_api_version: str = "2024-02-15-preview"
   ```

3. **Update `lifespan` in `main.py`:**
   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       global predictor, decision_service, trading_chain
       # Existing init...
       predictor = TradingPredictor(model_path)
       decision_service = DecisionService(predictor)
       # New: LangChain + Neo4j
       neo4j_client = Neo4jClient(settings.neo4j_uri, ...)
       trading_chain = TradingDecisionChain(neo4j_client, azure_config)
       yield
       # Cleanup
       neo4j_client.close()
   ```

4. **Update `docker-compose.yml` — ML service environment:**
   ```yaml
   ml-service:
     environment:
       # ... existing vars ...
       - NEO4J_URI=bolt://neo4j:7687
       - NEO4J_USER=neo4j
       - NEO4J_PASSWORD=${NEO4J_PASSWORD:-tradingrace2026}
       - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
       - AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}
       - AZURE_OPENAI_DEPLOYMENT=${AZURE_OPENAI_DEPLOYMENT:-gpt-4}
       - AZURE_OPENAI_API_VERSION=2024-02-15-preview
     depends_on:
       redis:
         condition: service_healthy
       neo4j:
         condition: service_healthy
   ```

5. **Update `/health` response** to include Neo4j and LangChain status:
   ```json
   {
     "status": "healthy",
     "model_loaded": true,
     "neo4j_connected": true,
     "langchain_ready": true
   }
   ```

**Exit Criteria:**
- `curl -X POST http://localhost:8000/decide` returns a valid decision with cited rules.
- `/health` reports Neo4j connection status.
- Existing `/predict` endpoint still works unchanged.

---

### Sprint 10b.4 — C# Backend Integration (2–3 days)

**Goal:** C# `AgentRunner` can route agents to the LangChain endpoint.

**Tasks:**

1. **Add new `ModelProvider` enum value:**
   ```csharp
   public enum ModelProvider
   {
       AzureOpenAi,
       Llama,
       CustomMl,
       LangChainGraphRag  // NEW
   }
   ```

2. **Create `LangChainAgentModelClient.cs` in `Infrastructure/Agents/`:**
   - Calls `POST http://ml-service:8000/decide` (instead of `/predict`).
   - Maps `AgentContext` → `AgentContextRequest` JSON.
   - Includes knowledge graph regime + rules in the request.
   - Parses response with `cited_rules` field.

3. **Register in `AgentModelClientFactory`:**
   ```csharp
   ModelProvider.LangChainGraphRag => _serviceProvider
       .GetRequiredService<LangChainAgentModelClient>(),
   ```

4. **Update `AgentContextBuilder` to include knowledge graph data:**
   - When `includeKnowledgeGraph = true`:
     - Call regime detector.
     - Pass detected regime ID in the context.
   - The Python service handles Neo4j queries internally.

5. **Seed a test agent with `ModelProvider = LangChainGraphRag`:**
   ```sql
   INSERT INTO Agents (Name, ModelProvider, ...)
   VALUES ('GraphRAG Agent', 'LangChainGraphRag', ...);
   ```

**Exit Criteria:**
- A `LangChainGraphRag` agent executes through the full `AgentRunner` pipeline.
- Decision is logged with `cited_rules` in the `AgentDecisions` table.
- Existing agents (AzureOpenAi, Llama, CustomMl) are unaffected.

---

### Sprint 10b.5 — Neo4j Audit Trail & Decision Graph (2–3 days)

**Goal:** Every LangChain decision is stored in Neo4j, linked to the rules it cited.

**Tasks:**

1. **Write decision audit nodes in Neo4j:**
   ```cypher
   CREATE (d:Decision {
       id: randomUUID(),
       agentId: $agentId,
       timestamp: datetime(),
       action: 'SELL',
       asset: 'BTC',
       quantity: 0.2,
       regime: 'VOLATILE',
       reasoning: 'High volatility detected...',
       portfolioValueBefore: 105000.0,
       portfolioValueAfter: 104800.0
   })
   WITH d
   MATCH (r:Rule {id: 'R003'})
   CREATE (d)-[:CITED]->(r)
   WITH d
   MATCH (r:Rule {id: 'R002'})
   CREATE (d)-[:CITED]->(r)
   WITH d
   MATCH (reg:Regime {id: 'VOLATILE'})
   CREATE (d)-[:DURING]->(reg)
   WITH d
   MATCH (a:Asset {symbol: 'BTC'})
   CREATE (d)-[:TRADED]->(a)
   ```

2. **Implement audit query endpoints in Python:**
   ```python
   @app.get("/audit/agent/{agent_id}")
   async def get_agent_decisions(agent_id: str, limit: int = 50):
       """Get decision history with rule citations from Neo4j."""

   @app.get("/audit/rule/{rule_id}")
   async def get_rule_citations(rule_id: str, limit: int = 50):
       """Get all decisions that cited a specific rule."""

   @app.get("/audit/regime/{regime_id}")
   async def get_regime_decisions(regime_id: str, limit: int = 50):
       """Get all decisions made during a specific regime."""
   ```

3. **Example audit Cypher queries:**
   ```cypher
   // "Why did the agent sell BTC?"
   MATCH (d:Decision {agentId: $agentId, asset: 'BTC', action: 'SELL'})-[:CITED]->(r:Rule)
   RETURN d.timestamp, d.reasoning, collect(r.id) AS cited_rules
   ORDER BY d.timestamp DESC LIMIT 10

   // "Which agents violated R001?"
   MATCH (d:Decision)-[:CITED]->(r:Rule {id: 'R001'})
   WHERE d.portfolioValueAfter < d.portfolioValueBefore
   RETURN d.agentId, d.timestamp, d.action, d.asset
   ORDER BY d.timestamp DESC

   // "Performance by regime"
   MATCH (d:Decision)-[:DURING]->(reg:Regime)
   RETURN reg.id,
          count(d) AS total_decisions,
          avg(d.portfolioValueAfter - d.portfolioValueBefore) AS avg_pnl
   ORDER BY avg_pnl DESC
   ```

**Exit Criteria:**
- Decisions are persisted in Neo4j after each agent run.
- `/audit/agent/{id}` returns decision history with rule citations.
- Neo4j Browser shows `Decision → CITED → Rule` relationships.

---

### Sprint 10b.6 — Testing, Documentation & Polish (2–3 days)

**Goal:** Full test coverage, updated documentation, CI/CD integration.

**Tasks:**

1. **Python tests:**
   - Unit tests for `Neo4jClient` (mock driver).
   - Unit tests for `TradingDecisionChain` (mock LLM + mock Neo4j).
   - Integration test: full `/decide` endpoint with real Neo4j testcontainer.
   - Integration test: `/audit/*` endpoints return correct data.

2. **C# tests:**
   - Unit test for `LangChainAgentModelClient` (mock HTTP).
   - Integration test for `AgentRunner` with `LangChainGraphRag` provider.

3. **Update CI/CD:**
   - Add Neo4j service to GitHub Actions workflow for integration tests.
     ```yaml
     services:
       neo4j:
         image: neo4j:5-community
         env:
           NEO4J_AUTH: neo4j/testpassword
         ports:
           - 7687:7687
     ```
   - Add LangChain dependencies to ML service CI.

4. **Documentation updates:**
   - `DEPLOYMENT_LOCAL.md` — Neo4j startup, seed script, Browser URL.
   - `TECHNICAL_ARCHITECTURE.md` — Updated architecture diagrams.
   - `README.md` — Add Neo4j and LangChain to tech stack table.
   - `DATABASE.md` — Document Neo4j data model alongside SQL schema.

5. **Update `scripts/seed-database.sh`:**
   - Call `scripts/seed-neo4j.sh` at the end of the existing seed flow.
   - Ensure idempotent (safe to run multiple times).

**Exit Criteria:**
- All tests pass (unit + integration).
- CI/CD pipeline includes Neo4j.
- Documentation is complete and accurate.
- `./scripts/seed-database.sh` seeds both SQL Server and Neo4j.

---

## 📐 File Inventory

### New Files

| File | Purpose |
|------|---------|
| `ai-trading-race-ml/app/graph/__init__.py` | Graph module init |
| `ai-trading-race-ml/app/graph/neo4j_client.py` | Neo4j driver wrapper |
| `ai-trading-race-ml/app/graph/queries.py` | Cypher query constants |
| `ai-trading-race-ml/app/chains/__init__.py` | LangChain chains module |
| `ai-trading-race-ml/app/chains/trading_chain.py` | LangChain decision pipeline |
| `ai-trading-race-ml/app/chains/prompts.py` | Prompt templates |
| `ai-trading-race-ml/app/models/langchain_schemas.py` | Pydantic models for LangChain output parsing |
| `AiTradingRace.Infrastructure/Agents/LangChainAgentModelClient.cs` | C# HTTP client for `/decide` |
| `scripts/seed-neo4j.sh` | Idempotent Neo4j seed script |
| `scripts/seed-neo4j.cypher` | Cypher seed statements |

### Modified Files

| File | Change |
|------|--------|
| `docker-compose.yml` | Add `neo4j` service + volume |
| `ai-trading-race-ml/requirements.txt` | Add `langchain`, `langchain-openai`, `neo4j` |
| `ai-trading-race-ml/app/config.py` | Add Neo4j + Azure OpenAI settings |
| `ai-trading-race-ml/app/main.py` | Add `/decide` endpoint, Neo4j lifecycle |
| `ai-trading-race-ml/app/models/schemas.py` | Add `cited_rules` to response model |
| `AiTradingRace.Domain/Entities/Agent.cs` | Add `LangChainGraphRag` to `ModelProvider` enum |
| `AiTradingRace.Infrastructure/Agents/AgentModelClientFactory.cs` | Register new client |
| `AiTradingRace.Infrastructure/DependencyInjection/ServiceCollectionExtensions.cs` | DI for new client |
| `.env.example` (all) | Add `NEO4J_*`, `AZURE_OPENAI_*` variables |
| `scripts/seed-database.sh` | Call `seed-neo4j.sh` |
| `DEPLOYMENT_LOCAL.md` | Neo4j instructions |
| `README.md` | Updated tech stack |

---

## 🔄 Migration Strategy

### Backward Compatibility

The migration is **fully additive** — no breaking changes:

1. **Existing agents are unaffected.**
   - `AzureOpenAi`, `Llama`, `CustomMl` providers continue to work as-is.
   - They still call the same endpoints, use the same prompts.

2. **New `/decide` endpoint is opt-in.**
   - Only agents with `ModelProvider = LangChainGraphRag` use it.
   - The existing `/predict` endpoint remains.

3. **`InMemoryKnowledgeGraphService` stays as fallback.**
   - If Neo4j is unavailable, the system can fall back to in-memory.
   - Feature flag: `UseNeo4jKnowledgeGraph` (default: `true`).

4. **Neo4j is optional in Docker Compose.**
   - If not started, LangChain agents gracefully degrade (skip graph context).
   - Other services are unaffected.

### Rollback Plan

If issues are found:
1. Set `ModelProvider = AzureOpenAi` for any LangChain agents.
2. Stop Neo4j container: `docker compose stop neo4j`.
3. No data loss — SQL Server still has all trades and decisions.

---

## 🧪 Testing Strategy

| Test Type | Scope | Tool |
|-----------|-------|------|
| **Unit** | Neo4j queries (mocked driver) | `pytest` + `unittest.mock` |
| **Unit** | LangChain chain (mocked LLM) | `pytest` + `langchain.testing` |
| **Unit** | C# HTTP client | `xUnit` + `MockHttpMessageHandler` |
| **Integration** | Full `/decide` flow | `pytest` + Neo4j testcontainer |
| **Integration** | C# → Python → Neo4j | `xUnit` + Docker Compose |
| **E2E** | AgentRunner → LangChain → Trade | Manual + automated smoke test |

---

## 📊 Success Metrics

| Metric | Target |
|--------|--------|
| LangChain agent decision latency (P95) | < 8 seconds |
| Neo4j subgraph query latency (P95) | < 50 ms |
| Decision audit query latency (P95) | < 100 ms |
| Rule citation accuracy | 100% of decisions cite at least 1 valid rule |
| Backward compatibility | 0 regressions on existing agents |
| Test coverage (new Python code) | > 85% |

---

## ⚠️ Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Neo4j adds container memory pressure | Medium | Low | Cap heap at 512 MB; monitor with `docker stats` |
| LangChain output parsing failures | Medium | Medium | Retry with structured output; fallback to raw JSON parse |
| Azure OpenAI API key management across services | Low | High | Single source of truth in `.env`; Key Vault for prod |
| LangChain library breaking changes | Low | Medium | Pin versions in `requirements.txt`; test on upgrade |
| Neo4j data drift from SQL Server | Low | Low | Neo4j is source of truth for rules; SQL for transactional data |

---

## 🗓️ Timeline

| Week | Sprint | Deliverable |
|------|--------|-------------|
| **Week 1** | 10b.1 + 10b.2 | Neo4j running + Python graph layer + LangChain chain |
| **Week 2** | 10b.3 + 10b.4 | `/decide` endpoint + C# integration |
| **Week 3** | 10b.5 + 10b.6 | Audit trail + tests + documentation |
| **Week 4** | Buffer | Bug fixes, optimization, polish |

---

## 🎯 Definition of Done

- [ ] Neo4j running in Docker Compose with seeded knowledge graph.
- [ ] `POST /decide` returns LangChain-generated decisions with rule citations.
- [ ] A `LangChainGraphRag` agent completes the full AgentRunner cycle.
- [ ] Decisions are auditable in Neo4j (`Decision -[:CITED]-> Rule`).
- [ ] Existing agents (`AzureOpenAi`, `Llama`, `CustomMl`) pass all existing tests.
- [ ] CI/CD updated with Neo4j service for integration tests.
- [ ] Documentation updated (`README`, `DEPLOYMENT_LOCAL`, `TECHNICAL_ARCHITECTURE`).
- [ ] All new code has tests with > 85% coverage.
