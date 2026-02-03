## Phase 1 – Architecture & solution .NET

**Objectif :** poser la base technique du projet.

**Tâches :**

- Créer la solution `.NET` avec les projets suivants :
  - `AiTradingRace.Web` → ASP.NET Core Web API (backend uniquement).
  - `AiTradingRace.Domain` → entités métier (Agent, Trade, Portfolio…).
  - `AiTradingRace.Application` → services métier, interfaces (use cases).
  - `AiTradingRace.Infrastructure` → EF Core, accès BD, appel APIs externes.
  - `AiTradingRace.Functions` → Azure Functions (market data, agents).
  - `ai-trading-race-web/` → Frontend React (Vite + TypeScript, séparé du backend).

- Configurer l’injection de dépendances (DI) :
  - Enregistrer les services de domaine / application dans `Web` et `Functions`.

- Définir les interfaces principales dans `Application` :
  - `IMarketDataProvider`
  - `IPortfolioService`
  - `IAgentRunner`
  - `IAgentModelClient` (abstraction sur les LLM).

**Critère de sortie :** la solution compile, les projets se voient entre eux, DI en place.

---

## Phase 2 – Modèle de données & base SQL

**Objectif :** définir et persister tous les objets métier.

**État actuel (07/12/2025) :** fondations EF livrées (`TradingDbContext`, contraintes, seeds BTC/ETH + agents, premières bougies). Services persistants EF (`EfMarketDataProvider`, `EfPortfolioService`) enregistrés en DI avec fallback in-memory si pas de `ConnectionStrings:TradingDb`. Web/Functions câblés sur la config. Migration initiale à générer/appliquer côté dev.

**Tâches prioritaires (restant à faire) :**

- P0 – Finaliser schéma
  - Générer la migration initiale + script SQL ; vérifier la création locale.
- P1 – Services persistants
  - Ajouter tests d’intégration (SQLite in-memory ou LocalDB) pour seed, ingestion candle, PnL +/-.
- P2 – Opérations
  - Documenter/automatiser la gestion des secrets (user-secrets, Key Vault) et ajouter logs ingestion/trades.

**Critère de sortie :** la BD se crée depuis les migrations, contient les seeds de base, et les services DI utilisent EF Core en dev (in-memory en fallback explicite).

---

## Phase 3 – Ingestion des données de marché

**Objectif :** stocker des prix crypto en base.

**Tâches :**

- Dans `Application` :
  - Définir un service `IMarketDataProvider` (signature propre).

- Dans `Infrastructure` :
  - Implémenter un `CoinGeckoMarketDataProvider` (ou Binance, peu importe).
  - Gérer :
    - Récupération des chandeliers (OHLC).
    - Mapping JSON → `MarketCandle`.
    - Persistance via `TradingDbContext`.

- Exposer un service `MarketDataIngestionService` qui :
  - Récupère les derniers prix.
  - Évite les doublons de candles.

- Créer un petit endpoint ou page admin pour lancer l’ingestion manuellement (utile avant d’avoir les Functions).

**Critère de sortie :** tu peux déclencher l’ingestion et voir des `MarketCandles` en base pour BTC/ETH.

---

## Phase 4 – Moteur de simulation (portefeuille & PnL)

**Objectif :** être capable de simuler des trades et d’actualiser la valeur d’un portefeuille.

**Tâches :**

- Dans `Application` :
  - Créer `IPortfolioService` :
    - Créer un portfolio pour un agent.
    - Appliquer un trade (achat/vente).
    - Recalculer les positions.
    - Calculer la valeur du portefeuille à partir des derniers prix.

  - Créer `IEquityService` :
    - Générer un `EquitySnapshot` à partir du portefeuille + prix.

- Dans `Infrastructure` :
  - Implémentations concrètes de ces services avec EF Core.

- Ajouter quelques tests unitaires (même simples) :
  - Cas de base : achat, vente, PnL positif, PnL négatif.

- Ajouter un endpoint API :
  - `GET /api/agents/{id}/equity` → renvoie la courbe d’equity (pour la future UI).

**Critère de sortie :** en insérant quelques trades à la main, tu vois la valeur du portefeuille évoluer et des snapshots se créer.

---

## Phase 5 – Intégration d’un premier agent IA

**Objectif :** brancher un premier LLM et obtenir des décisions de trading.

**Tâches :**

- Dans `Application` :
  - Définir un `AgentContext` (historique de prix, positions, cash).
  - Définir un `AgentDecision` (liste d’ordres normalisés).
  - Créer `IAgentModelClient` (interface pour interroger un modèle).

- Dans `Infrastructure` :
  - Implémenter `AzureOpenAiAgentModelClient` (ou autre provider que tu as).
  - Construire le prompt :
    - Règles (pas de levier, risque max, format JSON, etc.).
    - Contexte (quelques candles, positions, cash).

  - Parser la réponse en `AgentDecision` (JSON → C#).

- Dans `Application` :
  - Créer un `AgentRunner` :
    - Charge le contexte.
    - Appelle `IAgentModelClient`.
    - Valide et applique les trades via `IPortfolioService`.
    - Crée un `EquitySnapshot`.

- Ajouter un endpoint ou une commande interne :
  - Permet de lancer l’agent pour un cycle (ex. `RunAgentOnce(agentId)`).

**Critère de sortie :** tu peux déclencher un “tour” pour un agent, tu vois des trades générés par l’IA et la courbe d’equity se mettre à jour.

---

## Phase 5b – Intégration d'un modèle ML custom (Python + FastAPI)

**Objectif :** créer un agent piloté par un modèle ML entraîné maison (scikit-learn → PyTorch), exposé via une API Python.

**Architecture :**

```
┌─────────────────────┐       HTTP/REST        ┌────────────────────────┐
│  .NET Application   │  ───────────────────►  │   Python FastAPI       │
│  (AiTradingRace)    │                        │   (ML Model Service)   │
│                     │  ◄───────────────────  │   - scikit-learn       │
│  PyTorchAgentClient │      JSON Response     │   - PyTorch            │
└─────────────────────┘                        └────────────────────────┘
```

**Tâches :**

- Projet Python `ai-trading-race-ml/` :
  - Initialiser un projet Python (venv, requirements.txt ou Poetry/PDM).
  - Dépendances : `fastapi`, `uvicorn`, `pandas`, `scikit-learn`, `torch`, `pydantic`.
  - Structure suggérée :

    ```
    ai-trading-race-ml/
    ├── app/
    │   ├── main.py          # Endpoints FastAPI
    │   ├── models/          # Définitions de modèles Pydantic (AgentContext, AgentDecision)
    │   ├── ml/
    │   │   ├── trainer.py   # Scripts d'entraînement
    │   │   ├── predictor.py # Chargement du modèle + inférence
    │   │   └── model.pt     # Modèle sauvegardé (ou .pkl pour sklearn)
    │   └── config.py        # Configuration (chemins, hyperparamètres)
    ├── notebooks/           # Jupyter notebooks pour exploration
    ├── data/                # Datasets d'entraînement (candles historiques)
    ├── tests/
    ├── Dockerfile
    └── requirements.txt
    ```

- Endpoint FastAPI `/predict` :
  - Reçoit un `AgentContext` (JSON) : `candles[]`, `positions[]`, `cash`.
  - Retourne un `AgentDecision` (JSON) : `orders[]` avec `action`, `asset`, `quantity`.
  - Exemple de contrat :

    ```json
    // POST /predict
    {
      "candles": [{"timestamp": "...", "open": 100, "high": 105, "low": 98, "close": 102}],
      "positions": [{"asset": "BTC", "quantity": 0.5}],
      "cash": 5000.0
    }
    // Response
    {
      "orders": [{"action": "BUY", "asset": "ETH", "quantity": 0.2}]
    }
    ```

- Pipeline d'entraînement ML :
  - Charger les données historiques de `MarketCandle` (export depuis la BD ou via API).
  - Feature engineering : indicateurs techniques (RSI, SMA, MACD, etc.).
  - Entraînement avec scikit-learn (modèle baseline) puis migration vers PyTorch si besoin.
  - Sauvegarder le modèle (`model.pt` ou `model.pkl`).
  - Script CLI ou notebook pour ré-entraînement.

- Dans `AiTradingRace.Infrastructure` :
  - Implémenter `PyTorchAgentModelClient : IAgentModelClient` :
    - Appelle `POST http://<python-service>/predict`.
    - Mappe `AgentContext` → JSON request.
    - Parse la réponse JSON → `AgentDecision`.

  - Configurer l'URL du service Python via `appsettings.json` :

    ```json
    "PyTorchAgent": {
      "BaseUrl": "http://localhost:8000"
    }
    ```

- Dans `AiTradingRace.Domain` :
  - Ajouter un champ `ModelType` (enum) sur l'entité `Agent` : `LLM`, `CustomML`.
  - L'`AgentRunner` sélectionne le bon `IAgentModelClient` selon le type.

- Tests :
  - Test unitaire Python : endpoint `/predict` avec mock data.
  - Test d'intégration .NET : appeler le service Python local.

- Docker (optionnel mais recommandé) :
  - Dockerfile pour le service FastAPI.
  - `docker-compose.yml` pour lancer SQL + Python + .NET ensemble.

**Critère de sortie :** un agent de type `CustomML` peut être exécuté via l'AgentRunner, le modèle Python répond avec des ordres, et les trades sont appliqués comme pour un agent LLM.

---

## Phase 6 – Azure Functions (scheduler & automatisation)

**Objectif :** automatiser ingestion de marché + exécution des agents.

**Tâches :**

- Projet `AiTradingRace.Functions` :
  - Function timer `MarketDataFunction` :
    - Appelle `MarketDataIngestionService`.

  - Function timer `RunAgentsFunction` :
    - Liste tous les agents actifs.
    - Appelle `AgentRunner` pour chacun.

- (Optionnel plus avancé) :
  - Utiliser Azure Queue / Service Bus :
    - `RunAgentsFunction` envoie un message par agent.
    - Une Function queue-trigger traite chaque message (scalabilité).

- Configurer les `appsettings` / `local.settings.json` pour liaison BD, APIs externes.
- Tester les Functions en local (Azurite ou direct sur ton compte Azure).

**Critère de sortie :** les cycles “fetch market data” + “run all agents” peuvent tourner automatiquement via Functions.

---

## Phase 7 – UI React : dashboard & détail agent ✅ Terminée (19/01/2026)

**Objectif :** afficher visuellement la “course” entre les IA.

**Tâches :**

- Projet React `ai-trading-race-web/` :
  - Layout (sidebar/topbar).
  - Pages :
    - `/` → dashboard global.
    - `/agents` → liste des agents.
    - `/agents/{id}` → détail d’un agent.

- Dashboard global :
  - Appel à l’API pour récupérer :
    - La liste des agents.
    - La courbe d’equity de chaque agent (échantillonnée).

  - Intégration d’un composant de graphique (Recharts ou Chart.js).
  - Tableau leaderboard :
    - Nom agent, valeur actuelle, % de performance, drawdown éventuel.

- Page détail agent :
  - Mini graphique d’equity.
  - Tableau des trades récents.
  - Informations (stratégie, provider LLM, paramètres).

- Ajout de composants de chargement / erreurs (UX propre).

**Critère de sortie :** en ouvrant l’app, tu vois la course sous forme de graph, tu peux cliquer sur un agent pour voir son historique.

- Ajout de composants de chargement / erreurs (UX propre).

**Critère de sortie :** en ouvrant l'app, tu vois la course sous forme de graph, tu peux cliquer sur un agent pour voir son historique.

---

## Phase 8 – Infrastructure locale & CI/CD ✅ Terminée (20/01/2026)

**Objectif :** mettre en place l'infrastructure de développement local avec Docker et les pipelines d'intégration continue.

**État :** Phase complète avec Docker Compose, scripts d'automatisation, CI/CD GitHub Actions, et service ML avec idempotency.

**Sprints complétés :**

- **Sprint 8.1 – Llama API Integration ✅**
  - Intégration Groq (llama-3.3-70b-versatile).
  - `LlamaAgentModelClient` avec prompts structurés.
  - Configuration flexible (provider, model, temperature).
  - 13 tests d'intégration.

- **Sprint 8.3 – Security & Local Database Setup ✅**
  - Templates `.env.example` (Web, Functions, Frontend).
  - SQL Server 2022 dans `docker-compose.yml`.
  - Scripts d'automatisation :
    - `setup-database.sh` : création + migration.
    - `seed-database.sh` : 5 agents, 3 assets, 5 portfolios.
    - `generate-migration-script.sh` : export SQL.
  - Documentation complète (DATABASE.md 574 lignes, DEPLOYMENT_LOCAL.md 926 lignes).

- **Sprint 8.4 – GitHub Actions CI/CD ✅**
  - 7 workflows : backend, frontend, functions, ml-service, pr-checks, validate, ci orchestration.
  - Templates PR et issues.
  - Tests automatisés sur chaque push/PR.

- **Sprint 8.5 – ML Service & Redis ✅**
  - Docker Compose : SQL Server, Redis, ML Service.
  - Idempotency middleware avec Redis (20-50x amélioration).
  - Multi-stage Dockerfile optimisé (appuser non-root).
  - Health checks pour tous les services.

**Sprints différés (coûts Azure) :**

- **Sprint 8.2 – Azure Provisioning ⏸️**
  - Azure SQL Database, App Service, Functions, Key Vault.
  - Reporté pour éviter les frais mensuels en phase de développement.

- **Sprint 8.6 – Azure Deployment ⏸️**
  - Déploiement Static Web Apps, Container Apps.
  - Sera réalisé lors de la mise en production finale.

**Tests d'intégration (20/01/2026) :**

- 33/33 tests passés (23 statiques + 10 intégration).
- Infrastructure : Docker Compose, services, health checks.
- Database : création, schéma, seed data.
- Services : ML API, Redis cache, SQL Server.

**Issues résolues :**

1. Permissions Dockerfile (uvicorn binary non-exécutable).
2. Chemin sqlcmd (mssql-tools → mssql-tools18).
3. Certificat SQL Server (ajout flag -C).
4. Nom base de données (AiTradingRaceDb → AiTradingRace).

**Critère de sortie :** Infrastructure locale opérationnelle avec Docker Compose, base de données initialisée, données de test, CI/CD fonctionnel, documentation complète.

---

## Phase 8 (Azure) – Déploiement cloud ⏸️ Différé

**Objectif :** rendre le projet accessible en ligne et proprement configuré (reporté pour optimisation des coûts).

**Tâches (à réaliser lors de la mise en production) :**

- Créer les ressources Azure :
  - Azure SQL Database.
  - Azure Container Apps (ML Service).
  - Azure Static Web Apps (Frontend React).
  - Azure Functions (hébergement consumption).
  - Azure Cache for Redis.
  - Azure Key Vault (clés API LLM, chaînes de connexion).

- Ajouter les connexions ET secrets :
  - Chaîne de connexion SQL dans App Service / Functions via Key Vault ou config.
  - Clés d'API LLM dans Key Vault.

- Mettre en place le déploiement :
  - Build & publish depuis GitHub (GitHub Actions) vers :
    - Container Apps (ML Service).
    - Static Web Apps (Frontend).
    - Functions.

- Configurer les migrations de BD au démarrage (ou script SQL dédié).

**Critère de sortie :** l'application est accessible via une URL Azure, les Functions tournent, les données sont stockées dans Azure SQL, et le service ML gère l'idempotency avec Azure Cache for Redis.

> **Note :** Les workflows GitHub Actions pour Azure deployment sont déjà configurés dans `.github/workflows/`. L'activation nécessitera uniquement la configuration des secrets GitHub et la création des ressources Azure.

---

## Phase 9 – RabbitMQ Message Queue & Horizontal Scalability

**Objectif :** transformer l'architecture séquentielle en système distribué avec traitement parallèle des agents via RabbitMQ et idempotency keys.

**Motivations :**

- **Performance** : passer de l'exécution séquentielle (5 agents × 10s = 50s) à l'exécution parallèle (5 agents en ~10-15s).
- **Scalabilité** : permettre le déploiement de multiples workers pour traiter 100+ agents simultanément.
- **Résilience** : isoler les échecs d'agents individuels sans bloquer le traitement des autres.
- **Foundation** : poser les bases pour un système horizontalement scalable.

**Architecture actuelle (problèmes) :**

```
[Timer Function: RunAgentsFunction]
    ↓ foreach agent (sequential)
    ├─ Agent 1 (10s) → LLM call → DB transaction
    ├─ Agent 2 (10s) → LLM call → DB transaction
    ├─ Agent 3 (10s) → LLM call → DB transaction
    └─ Agent 4 (10s) → LLM call → DB transaction
    
Total: 40+ seconds
Problem: Sequential, single point of failure, no scalability
```

**Architecture cible (avec RabbitMQ) :**

```
[Timer Function: PublishAgentsFunction] (< 1s)
    ↓ Publish messages to queue
[RabbitMQ Queue: agent-execution]
    ↓ Multiple consumers in parallel
    ├─ [Worker 1] → Agent 1 (10s)
    ├─ [Worker 2] → Agent 2 (10s)
    ├─ [Worker 3] → Agent 3 (10s)
    └─ [Worker N] → Agent N (10s)
    
Total: ~10-15 seconds
Benefits: Parallel, fault-tolerant, horizontally scalable
```

**Tâches :**

### **Sprint 9.1 – RabbitMQ Infrastructure Setup**

- **Docker Compose :**
  - Ajouter service RabbitMQ (image `rabbitmq:3.12-management`).
  - Exposer ports : 5672 (AMQP), 15672 (Management UI).
  - Configuration : utilisateur/mot de passe, vhosts.
  - Health check : `rabbitmq-diagnostics ping`.

- **NuGet Packages :**
  - Ajouter `RabbitMQ.Client` à `AiTradingRace.Infrastructure`.
  - Ajouter `Microsoft.Extensions.Hosting` pour background services.

- **Configuration :**
  - `appsettings.json` : section RabbitMQ (host, port, user, password, queues).
  - Environment variables pour secrets.

### **Sprint 9.2 – Message Publishing (Timer Function)**

- **Nouvelle Function : `PublishAgentsFunction` :**
  - Timer trigger : `0 */30 * * * *` (every 30 minutes).
  - Attribut `[Singleton]` pour éviter les exécutions multiples.
  - Logique :
    1. Query active agents from database.
    2. Generate execution cycle ID (timestamp-based).
    3. Publish one message per agent to RabbitMQ queue.
    4. Each message contains: AgentId, ExecutionCycleId, Timestamp.

- **Message Format :**
  ```json
  {
    "agentId": "guid",
    "executionCycleId": "20260122-1430",
    "timestamp": "2026-01-22T14:30:00Z",
    "idempotencyKey": "agent-run:guid:20260122-1430"
  }
  ```

- **Infrastructure Service : `IRabbitMqPublisher` :**
  - Interface pour abstraire la publication de messages.
  - Implémentation avec retry policy (Polly).
  - Logging structuré (correlation IDs).

### **Sprint 9.3 – Idempotency Layer with Redis**

- **Extension Redis Usage :**
  - Réutiliser le service Redis existant (déjà dans docker-compose).
  - Créer `IIdempotencyService` dans Application layer.
  - Implémentation `RedisIdempotencyService` dans Infrastructure.

- **Idempotency Logic :**
  ```csharp
  public interface IIdempotencyService
  {
      Task<bool> TryAcquireLockAsync(string idempotencyKey, string workerId, TimeSpan expiry);
      Task<bool> IsAlreadyProcessedAsync(string idempotencyKey);
      Task MarkAsCompletedAsync(string idempotencyKey, object result);
      Task<T?> GetCachedResultAsync<T>(string idempotencyKey);
  }
  ```

- **Key Structure :**
  - Lock key: `agent-lock:{agentId}:{executionCycleId}`
  - Result key: `agent-result:{agentId}:{executionCycleId}`
  - TTL: 1 hour (prevents stale locks).

### **Sprint 9.4 – Worker Service (Message Consumer)**

- **Background Service : `AgentWorkerService` :**
  - Hosted service qui consomme les messages de la queue RabbitMQ.
  - Configuration : nombre de workers concurrents (default: 3).
  - Implémentation dans `AiTradingRace.Functions` ou nouveau projet `AiTradingRace.Workers`.

- **Message Processing Flow :**
  1. Receive message from queue.
  2. Extract idempotency key.
  3. Check Redis: `IsAlreadyProcessedAsync(key)`.
     - If true → Acknowledge message, skip processing.
  4. Attempt lock: `TryAcquireLockAsync(key, workerId)`.
     - If false → Another worker processing, acknowledge and skip.
  5. Execute agent: `await _agentRunner.RunAgentOnceAsync(agentId)`.
  6. On success:
     - Store result in Redis: `MarkAsCompletedAsync(key, result)`.
     - Acknowledge message to RabbitMQ.
  7. On failure:
     - Log error.
     - Nack message with requeue (max 3 retries).
     - After max retries → send to Dead Letter Queue.

- **Dead Letter Queue (DLQ) :**
  - Queue : `agent-execution-dlq`.
  - Stores failed messages for manual inspection.
  - Monitoring endpoint: `GET /api/admin/failed-agents`.

### **Sprint 9.5 – Observability & Monitoring**

- **RabbitMQ Management UI :**
  - Accessible à `http://localhost:15672`.
  - Monitoring : queue depth, message rate, consumers.

- **Structured Logging :**
  - Correlation IDs propagated across publishers/workers.
  - Log enrichment : workerId, agentId, executionCycleId.

- **Metrics :**
  - Messages published/consumed per minute.
  - Worker processing time (P50, P95, P99).
  - Failed agents count.
  - Queue backlog size.

- **Health Checks :**
  - RabbitMQ connection health.
  - Redis connection health.
  - Worker liveness check.

### **Sprint 9.6 – Testing & Validation**

- **Unit Tests :**
  - `IdempotencyService` : lock acquisition, duplicate detection.
  - `RabbitMqPublisher` : message serialization, retry logic.

- **Integration Tests :**
  - End-to-end flow : publish → consume → process → acknowledge.
  - Idempotency : same message processed twice → only one execution.
  - Failure scenarios : worker crash → message requeued → successful retry.
  - DLQ : message fails 3 times → routed to DLQ.

- **Load Tests :**
  - Scenario 1 : 5 workers, 20 agents → verify parallel processing.
  - Scenario 2 : 10 workers, 100 agents → measure throughput.
  - Scenario 3 : 1 worker fails mid-processing → verify recovery.

- **Manual Testing :**
  - RabbitMQ UI : visualize message flow.
  - Redis : inspect idempotency keys.
  - Logs : trace agent execution across publisher/worker.

### **Sprint 9.7 – Migration & Deprecation**

- **Deprecate `RunAgentsFunction` :**
  - Rename to `RunAgentsFunction.OLD.cs`.
  - Add deprecation warning in logs.
  - Keep for rollback safety during migration.

- **Configuration Toggle :**
  - Feature flag : `UseMessageQueue` (default: true).
  - If false → fallback to old sequential function.

- **Documentation :**
  - Update `DEPLOYMENT_LOCAL.md` : RabbitMQ setup instructions.
  - Create `ARCHITECTURE_DISTRIBUTED.md` : explain message flow.
  - Update `SERVICES_SCHEMA.md` : add RabbitMQ components.

**Bénéfices attendus :**

| Métrique | Avant | Après | Amélioration |
|----------|-------|-------|--------------|
| **Temps d'exécution** (5 agents) | 50s | 10-15s | 3-5x plus rapide |
| **Throughput** (agents/heure) | ~360 | ~1800+ | 5x+ |
| **Résilience** | Échec bloque tout | Échecs isolés | Fault-tolerant |
| **Scalabilité** | 1 instance fixe | N workers | Horizontale |
| **Coût** | $0 | $0 | Aucun (open source) |

**Limitations connues (à adresser plus tard) :**

- ⚠️ **Database bottleneck** : à 100+ agents, SQL Server devient le goulot. Solution : read replicas, connection pooling tuning.
- ⚠️ **Timer function duplication** : si Azure Functions scale-out activé. Solution : déjà géré par `[Singleton]` attribute.
- ⚠️ **External API rate limits** : Groq/CoinGecko. Solution : déjà géré par circuit breakers et rate limiting handlers.

**Critère de sortie :** 
- RabbitMQ opérationnel dans Docker Compose avec Management UI.
- PublishAgentsFunction publie des messages avec idempotency keys.
- AgentWorkerService consomme et traite les agents en parallèle.
- Idempotency garantit qu'aucun agent n'est exécuté deux fois dans le même cycle.
- Dead Letter Queue capture les échecs persistants.
- Tests d'intégration validés (100% success rate).
- Documentation mise à jour avec architecture distribuée.
- Performance mesurée : 3-5x amélioration sur 5 agents.

---

## Phase 10 – Monitoring, sécurité minimale & polish CV

**Objectif :** rendre le projet "propre" aux yeux d'un recruteur.
**Objectif :** rendre le projet “propre” aux yeux d’un recruteur.

**Tâches :**

- Activer Application Insights sur :
  - App Service.
  - Azure Functions.

- Ajouter des logs côté code :
  - Exécution des agents (agent, temps de réponse, erreurs).
  - Appels aux APIs externes (succès / échecs).

- **OpenTelemetry (distributed tracing) :**
  - Configurer OpenTelemetry dans .NET et Python.
  - Propager `traceparent` / `X-Request-Id` headers.
  - Exporter vers Azure Monitor / Application Insights.
  - Métriques : latence ML, taux d'erreur, distribution BUY/SELL/HOLD.

- Gérer les erreurs UI :
  - Messages d’erreur clairs en cas de problème API.
  - Gestion des états “pas de data”.

- Documentation :
  - Compléter le `README.md` :
    - Description du projet.
    - Architecture (schéma texte ou image).
    - Stack technique détaillée.
    - Instructions pour lancer en local.
    - Lien vers la version déployée.

**Critère de sortie :** le projet est documenté, monitoré et prêt à être présenté.

---

## Phase 10 – GraphRAG-lite : Décisions explicables & Audit Trail

**Objectif :** permettre aux agents IA de citer explicitement les règles et contraintes qui justifient leurs décisions de trading, avec traçabilité complète.

**Motivations :**

- Répondre à la question : "Pourquoi l'agent a-t-il acheté ETH à ce moment ?"
- Créer un audit trail exploitable pour l'analyse post-mortem.
- Forcer le LLM à raisonner dans le cadre défini (règles de risque, régimes de marché).

**Architecture :**

```
┌─────────────────────────────────────────────────────────────────┐
│                     KNOWLEDGE GRAPH (Lite)                      │
├─────────────────────────────────────────────────────────────────┤
│  NODES:                                                         │
│  ├── Rule:R001 "MaxPositionSize" {threshold: 50%, severity: H}  │
│  ├── Rule:R002 "MinCashReserve" {threshold: $100, severity: M}  │
│  ├── Regime:VOLATILE {volatility: >5%/day}                      │
│  ├── Regime:BULLISH {trend: positive 7d MA}                     │
│  └── Asset:BTC, Asset:ETH                                       │
│                                                                 │
│  EDGES:                                                         │
│  ├── BTC --tradable--> Rule:R001                                │
│  ├── Regime:VOLATILE --activates--> Rule:R002 (stricter)        │
│  └── Regime:BULLISH --relaxes--> Rule:R003                      │
└─────────────────────────────────────────────────────────────────┘
```

**Tâches :**

- Dans `Domain` :
  - Définir les entités du graphe de connaissances :
    - `RuleNode` : ID, nom, description, seuil, sévérité.
    - `RegimeNode` : ID, nom, conditions d'activation.
    - `RuleEdge` : relation entre nœuds (activates, relaxes, appliesTo).
  - Créer l'entité `DecisionLog` pour l'audit trail :
    - AgentId, Timestamp, Action, Asset, Rationale, CitedNodeIds[], SubgraphSnapshot.

- Dans `Application` :
  - Créer `IKnowledgeGraphService` :
    - Charger le graphe de règles/régimes.
    - Extraire un sous-graphe pertinent selon le contexte courant.
    - Sérialiser le sous-graphe en JSON pour injection dans le prompt.
  - Créer `IRegimeDetector` :
    - Analyser les candles récents pour détecter le régime de marché (volatile, bullish, bearish, stable).
  - Étendre `IAgentContextBuilder` :
    - Inclure le sous-graphe pertinent dans le contexte agent.

- Dans `Infrastructure` :
  - Implémenter `InMemoryKnowledgeGraphService` (graphe léger, ~20-30 nœuds).
  - Implémenter `VolatilityBasedRegimeDetector`.
  - Modifier le prompt LLM pour :
    - Injecter le sous-graphe des règles applicables.
    - Exiger que l'agent cite les IDs de nœuds dans sa réponse.
  - Parser les citations de la réponse LLM et les stocker avec la décision.

- Dans `Web` :
  - Endpoint `GET /api/agents/{id}/decisions` : historique des décisions avec citations.
  - Endpoint `GET /api/agents/{id}/decisions/{decisionId}` : détail avec sous-graphe visualisable.

- Dans le Frontend React :
  - Visualisation du graphe de règles citées par décision.
  - Filtrage de l'historique par règle violée/respectée.

- Tests :
  - Tests unitaires pour `KnowledgeGraphService` et `RegimeDetector`.
  - Tests d'intégration pour le flux complet (contexte → LLM → parsing citations → audit).

**Critère de sortie :** chaque décision d'agent inclut les citations de règles, le régime de marché détecté, et un audit trail complet permet de tracer le raisonnement de l'IA.
