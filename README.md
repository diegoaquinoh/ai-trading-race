# ai-trading-race

Course entre agents IA de trading (LLM) qui pilotent chacun un portefeuille crypto simulé. Les prix de marché sont ingérés depuis CoinGecko, les agents décident (buy/sell/hold), et le dashboard React affiche l'equity et le classement.

## 🔄 CI/CD Status

![Backend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Backend%20CI%2FCD/badge.svg?branch=main)
![Functions CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Azure%20Functions%20CI%2FCD/badge.svg?branch=main)
![Frontend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Frontend%20CI%2FCD/badge.svg?branch=main)
![ML Service CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/ML%20Service%20CI%2FCD/badge.svg?branch=main)

## 📊 Statut du Projet

| Phase    | Description                            | Status      |
| -------- | -------------------------------------- | ----------- |
| Phase 1  | Architecture & Solution .NET           | ✅ Terminée |
| Phase 2  | Modèle de données & Base SQL           | ✅ Terminée |
| Phase 3  | Ingestion des données de marché        | ✅ Terminée |
| Phase 4  | Moteur de simulation (Portfolio & PnL) | ✅ Terminée |
| Phase 5  | Intégration agents IA (LLM)            | ✅ Terminée |
| Phase 5b | Modèle ML custom (Python + FastAPI)    | ✅ Terminée |
| Phase 6  | Azure Functions (scheduler)            | ✅ Terminée |
| Phase 7  | UI React Dashboard                     | ✅ Terminée |
| Phase 8  | CI/CD & Local Deployment               | ✅ Terminée (Sprint 8.3, 8.4, 8.5) |
| Phase 9  | Monitoring & Sécurité                  | ⏳ À venir  |
| Phase 10 | GraphRAG-lite (Explainable AI)         | ⏳ À venir  |

**Phase 8 Details:**
- ✅ Sprint 8.1: Llama API Integration (Groq)
- ⏸️ Sprint 8.2: Azure Provisioning (deferred - costs)
- ✅ Sprint 8.3: Security & Local Database Setup
- ✅ Sprint 8.4: GitHub Actions CI/CD (7 workflows)
- ✅ Sprint 8.5: ML Service & Redis (Docker Compose)
- ⏸️ Sprint 8.6: Azure Deployment (deferred - costs)

## Architecture

```
ai-trading-race/
├── AiTradingRace.Web/           # ASP.NET Core Web API (backend)
├── AiTradingRace.Domain/        # Entités métier (Agent, Asset, Candle, Portfolio...)
├── AiTradingRace.Application/   # Interfaces & DTOs (IMarketDataProvider, IPortfolioService...)
├── AiTradingRace.Infrastructure/# Implémentations EF Core, clients API externes
├── AiTradingRace.Functions/     # Azure Functions (timers pour ingestion & agents)
├── AiTradingRace.Tests/         # Tests unitaires (xUnit + Moq)
├── ai-trading-race-web/         # Frontend React (Vite + TypeScript)
└── ai-trading-race-ml/          # Service Python FastAPI (modèle ML custom)
```

## Prérequis

- **Docker Desktop** (pour SQL Server, Redis, ML Service)
- **.NET 8 SDK** (pour backend API)
- **Node.js 20+** (pour frontend React)
- **Python 3.11+** (pour ML service - optionnel si Docker)
- **Azure Functions Core Tools v4** (pour scheduler - optionnel)

### Installation sur macOS (Apple Silicon)

```bash
# Installer .NET 8 SDK via Homebrew
brew install dotnet@8
brew link dotnet@8 --force

# Ajouter au PATH (ajouter à ~/.zshrc pour rendre permanent)
export PATH="/opt/homebrew/opt/dotnet@8/bin:$PATH"

# Installer les outils EF Core
dotnet tool install --global dotnet-ef
export PATH="$HOME/.dotnet/tools:$PATH"

# Vérifier l'installation
dotnet --version  # Devrait afficher 8.x.x
```

### Installation sur Windows/Linux

```bash
# Télécharger .NET 8 SDK depuis https://dotnet.microsoft.com/download
# Ou via package manager (apt, winget, etc.)
dotnet tool install --global dotnet-ef
```

## 🚀 Démarrage Rapide (Local)

> **Note:** Voir [DEPLOYMENT_LOCAL.md](./DEPLOYMENT_LOCAL.md) pour le guide complet

### 1. Configurer les variables d'environnement

```bash
# Copier le fichier d'exemple (single source of truth)
cp .env.example .env

# Éditer .env avec vos valeurs
# Minimum requis: SA_PASSWORD, Llama__ApiKey
nano .env
```

> **⚠️ IMPORTANT - Mot de passe SQL Server:**  
> Le mot de passe `SA_PASSWORD` doit respecter la politique de complexité Azure SQL:
> - Minimum 8 caractères
> - Au moins 1 majuscule, 1 minuscule, 1 chiffre
> - **Au moins 1 caractère spécial** (`@`, `#`, `$`, etc.)
> - **Évitez `!`** sur macOS/zsh (conflit avec l'expansion d'historique)
> - Exemple valide: `YourStrong@Passw0rd123`

> **📝 Note:** Le projet utilise UN SEUL fichier `.env` à la racine pour toute la configuration.  
> Ce fichier est lu par Docker Compose, les scripts, et peut être sourcé pour les applications.

### 2. Démarrer l'infrastructure (Docker Compose)

```bash
# Docker Compose lit automatiquement le fichier .env
docker compose up -d
```

Cela démarre:
- SQL Server 2022 (port 1433)
- Redis 7 (port 6379)
- ML Service FastAPI (port 8000)

### 3. Initialiser la base de données

```bash
# Charger les variables d'environnement
source .env

# Créer le schéma (détecte automatiquement si déjà existant)
./scripts/setup-database.sh

# Insérer les données de test (BTC, ETH, 5 agents)
./scripts/seed-database.sh
```

### 4. Configurer les Azure Functions

```bash
# Les Functions utilisent local.settings.json (format spécifique Azure)
cp AiTradingRace.Functions/local.settings.json.example \
   AiTradingRace.Functions/local.settings.json

# Copier les valeurs depuis .env (notamment Llama__ApiKey)
nano AiTradingRace.Functions/local.settings.json
```

### 5. Démarrer les services

> **⚠️ IMPORTANT:** Vous devez exécuter `source .env` dans **CHAQUE terminal** avant de démarrer un service!

```bash
# Terminal 1: Azure Functions (collecte de données + agents)
source .env  # ← OBLIGATOIRE dans ce terminal
cd AiTradingRace.Functions
func start

# Terminal 2: Backend API
source .env  # ← OBLIGATOIRE dans ce terminal
cd AiTradingRace.Web
dotnet run

# Terminal 3: Frontend Dashboard
cd ai-trading-race-web
npm install
npm run dev
```

**Pourquoi `source .env` est nécessaire:**
- Le backend (.NET) a besoin de `ConnectionStrings__TradingDb` pour se connecter à SQL Server
- Les Azure Functions ont besoin des mêmes variables pour l'ingestion des données
- Sans cela, vous obtiendrez des erreurs **"Login failed for user 'sa'"**

### 6. Accéder à l'application

- **Dashboard:** http://localhost:5173
- **API:** http://localhost:5001/swagger
- **ML Service:** http://localhost:8000/docs
- **Functions:** http://localhost:7071

## 🛠 Scripts Utiles

```bash
# Voir les logs des services Docker
docker compose logs -f sqlserver
docker compose logs -f redis
docker compose logs -f ml-service

# Vérifier l'état des conteneurs
docker compose ps

# Redémarrer un service
docker compose restart sqlserver

# Arrêter tous les services
docker compose down

# Reset complet de la base de données
source .env
docker exec ai-trading-sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$SA_PASSWORD" -C \
  -Q "DROP DATABASE AiTradingRace;"
./scripts/setup-database.sh
./scripts/seed-database.sh
```

## � Troubleshooting

### "Login failed for user 'sa'"
1. **Vérifiez le mot de passe** - Doit contenir un caractère spécial (`@`, pas `!`)
2. **Volume Docker persistant** - Si vous changez le mot de passe, supprimez le volume:
   ```bash
   docker compose down -v  # Supprime les volumes
   docker compose up -d    # Recrée avec le nouveau mot de passe
   ```
3. **Variable d'environnement** - Le backend doit avoir `ConnectionStrings__TradingDb` défini

### "Could not find dotnet" (macOS)
```bash
# Ajouter au PATH (ou dans ~/.zshrc)
export PATH="/opt/homebrew/opt/dotnet@8/bin:$PATH"
export PATH="$HOME/.dotnet/tools:$PATH"
```

### SQL Server container "unhealthy"
```bash
# Vérifier les logs
docker logs ai-trading-sqlserver --tail 50

# Si erreur de mot de passe, reset complet:
docker compose down -v && docker compose up -d
```

### Appliquer les migrations EF Core manuellement
```bash
export ConnectionStrings__TradingDb='Server=localhost,1433;Database=AiTradingRace;User Id=sa;Password=YourStrong@Passw0rd123;TrustServerCertificate=True'
dotnet ef database update --project AiTradingRace.Infrastructure --startup-project AiTradingRace.Web
```

## �📚 Documentation

- [DATABASE.md](./DATABASE.md) - Guide base de données (connexions, migrations, troubleshooting)
- [scripts/README.md](./scripts/README.md) - Guide des scripts de base de données
- [DEPLOYMENT_LOCAL.md](./DEPLOYMENT_LOCAL.md) - Guide déploiement local complet
- [TEST_RESULTS.md](./TEST_RESULTS.md) - Résultats des tests (23 static + 10 integration)
- [PLANNING_PHASE8.md](./PLANNING_PHASE8.md) - Détails Phase 8 (CI/CD)

## 🔒 Sécurité

- **Mots de passe:** Configurés via variables d'environnement (`.env`)
- **Secrets:** Fichier `.env` exclu de Git (`.gitignore`)
- **API Keys:** Stockées dans `local.settings.json` (non versionné)
- **Production:** Utiliser Azure Key Vault ou secrets managés

## ⚙️ Variables d'Environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `SA_PASSWORD` | `YourStrong@Passw0rd123` | Mot de passe SQL Server (⚠️ doit contenir `@` ou `#`, pas `!`) |
| `SQL_CONTAINER_NAME` | `ai-trading-sqlserver` | Nom du conteneur |
| `SQL_DATABASE_NAME` | `AiTradingRace` | Nom de la base |
| `STARTING_BALANCE` | `100000.00` | Capital initial des portfolios |
| `ML_SERVICE_API_KEY` | `test-api-key-12345` | Clé API du service ML |

Voir [`.env.example`](./.env.example) pour la liste complète.

---

## Démarrage rapide (Legacy - sans Docker Compose)

### 1. Base de données (Docker SQL Server)

```bash
docker run -d --name sqlserver \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=Project!Azure0" \
  -p 1433:1433 mcr.microsoft.com/mssql/server:2022-latest
```

### 2. Configuration des secrets

```bash
dotnet user-secrets set "ConnectionStrings:TradingDb" \
  "Server=localhost,1433;Database=AiTradingRace;User Id=sa;Password=Project!Azure0;Encrypt=True;TrustServerCertificate=True;" \
  --project AiTradingRace.Web
```

### 3. Appliquer les migrations

```bash
export ConnectionStrings__TradingDb="Server=localhost,1433;Database=AiTradingRace;User Id=sa;Password=Project!Azure0;Encrypt=True;TrustServerCertificate=True;"
dotnet ef database update -p AiTradingRace.Infrastructure -s AiTradingRace.Web
```

### 4. Lancer l'API

```bash
dotnet run --project AiTradingRace.Web
```

### 5. Tester l'ingestion de données

```bash
curl -k -X POST https://localhost:7240/api/admin/ingest
```

## Ingestion des données de marché

L'API se connecte à **CoinGecko** pour récupérer les chandeliers OHLC des cryptos (BTC, ETH).

| Endpoint                          | Description                                     |
| --------------------------------- | ----------------------------------------------- |
| `POST /api/admin/ingest`          | Ingère les candles pour tous les actifs activés |
| `POST /api/admin/ingest/{symbol}` | Ingère les candles pour un actif spécifique     |

**Configuration** (`appsettings.json`):

```json
{
  "CoinGecko": {
    "BaseUrl": "https://api.coingecko.com/api/v3/",
    "TimeoutSeconds": 30,
    "DefaultDays": 1
  }
}
```

## API Endpoints – Portfolio & Equity (Phase 4)

| Method | Endpoint                              | Description                   |
| ------ | ------------------------------------- | ----------------------------- |
| GET    | `/api/agents`                         | Liste des agents (classement) |
| GET    | `/api/agents/{id}`                    | Détails agent + performance   |
| GET    | `/api/agents/{id}/portfolio`          | État du portefeuille          |
| POST   | `/api/agents/{id}/portfolio/trades`   | Exécuter des trades manuels   |
| GET    | `/api/agents/{id}/trades`             | Historique des trades         |
| GET    | `/api/agents/{id}/equity`             | Courbe d'équité               |
| GET    | `/api/agents/{id}/equity/latest`      | Dernier snapshot              |
| POST   | `/api/agents/{id}/equity/snapshot`    | Capturer un snapshot          |
| GET    | `/api/agents/{id}/equity/performance` | Métriques de performance      |

## Tests

```bash
# Exécuter tous les tests
dotnet test

# Tests avec détails
dotnet test --verbosity normal
```

**Couverture actuelle (81 tests):**

- `CoinGeckoMarketDataClientTests` : Parsing JSON, erreurs HTTP, validation
- `MarketDataIngestionServiceTests` : Insertion, déduplication, gestion des assets
- `EquityServiceTests` : Snapshots, courbe d'équité, métriques de performance
- `PortfolioEquityIntegrationTests` : Flux complet portfolio + trades
- `SqlServerIntegrationTests` : Tests Testcontainers contre SQL Server réel
- `RiskValidatorTests` : Validation des contraintes de risque
- `AgentContextBuilderTests` : Construction du contexte agent
- `FunctionTests` : Tests Azure Functions (MarketData, RunAgents, EquitySnapshot)

## Migrations EF Core

```bash
# Ajouter une migration
dotnet ef migrations add <Name> -p AiTradingRace.Infrastructure -s AiTradingRace.Web

# Appliquer les migrations
dotnet ef database update -p AiTradingRace.Infrastructure -s AiTradingRace.Web
```

## Frontend React

```bash
cd ai-trading-race-web
npm install
npm run dev
```

Le dashboard affiche :

- Liste des agents et leur performance
- Courbe d'equity par agent
- Historique des trades

## Structure des entités

| Entité           | Description                                         |
| ---------------- | --------------------------------------------------- |
| `Agent`          | Agent IA avec nom, provider (GPT/Claude/Grok)       |
| `MarketAsset`    | Actif tradable (BTC, ETH) avec ExternalId CoinGecko |
| `MarketCandle`   | Chandelier OHLC avec timestamp UTC                  |
| `Portfolio`      | Portefeuille lié à un agent                         |
| `Position`       | Position ouverte sur un actif                       |
| `Trade`          | Ordre exécuté (Buy/Sell)                            |
| `EquitySnapshot` | Valeur du portfolio à un instant T                  |
| `DecisionLog`    | Décision IA avec citations de règles (Phase 10)     |

## 🛡️ Production Enhancements

| Enhancement                   | Phase | Description                                                   |
| ----------------------------- | ----- | ------------------------------------------------------------- |
| **Contract Versioning**       | 5b    | `schemaVersion`, `modelVersion`, `requestId` in API contracts |
| **Structured Explainability** | 5b    | `ExplanationSignal` with feature contributions                |
| **API Key Security**          | 5b    | Service-to-service authentication (`X-API-Key`)               |
| **Idempotency**               | 8     | Redis cache for retry safety                                  |
| **OpenTelemetry**             | 9     | Distributed tracing across .NET ↔ Python                      |

## 🧠 GraphRAG-lite : Décisions Explicables (Phase 10)

Fonctionnalité avancée permettant de tracer et expliquer les décisions des agents IA.

### Concept

```
┌──────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│  Knowledge Graph │ ──► │   LLM + Subgraph    │ ──► │  Decision Log   │
│  (Rules/Regimes) │     │   (Cite node IDs)   │     │  (Audit Trail)  │
└──────────────────┘     └─────────────────────┘     └─────────────────┘
```

### Fonctionnalités

| Feature                    | Description                                                |
| -------------------------- | ---------------------------------------------------------- |
| **Graphe de règles**       | Nœuds pour chaque contrainte de risque (MaxPosition, etc.) |
| **Régimes de marché**      | Détection automatique : volatile, bullish, bearish, stable |
| **Citations obligatoires** | Le LLM doit citer les IDs de nœuds dans sa réponse         |
| **Audit trail**            | Chaque décision stockée avec sous-graphe et explications   |

### Exemple de réponse LLM avec citations

```json
{
  "action": "BUY",
  "asset": "ETH",
  "quantity": 0.5,
  "rationale": "ETH stable per [Regime:STABLE]. Position compliant with [R001:MaxPosition]. Cash reserves OK per [R002:MinCashReserve].",
  "cited_nodes": ["Regime:STABLE", "R001", "R002"]
}
```

## 🤖 Phase 5b: Custom ML Service

Python FastAPI service for ML-based trading decisions.

### Quick Start

```bash
# Option 1: Run locally
cd ai-trading-race-ml
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Option 2: Run with Docker
cd ai-trading-race-ml
docker build -t ai-trading-ml .
docker run -p 8000:8000 -e ML_SERVICE_API_KEY=your-key ai-trading-ml
```

### API Endpoints

| Method | Path       | Auth | Description               |
| ------ | ---------- | ---- | ------------------------- |
| GET    | `/health`  | ❌   | Health check              |
| POST   | `/predict` | ✅   | Generate trading decision |

### Configuration

Set via environment variables (`ML_SERVICE_` prefix):

| Variable        | Default                    | Description                         |
| --------------- | -------------------------- | ----------------------------------- |
| `MODEL_PATH`    | `models/trading_model.pkl` | Path to trained model               |
| `MODEL_VERSION` | `1.0.0`                    | Model version string                |
| `API_KEY`       | `""`                       | API key for auth (empty = disabled) |

> **Note:** Initial model uses `scikit-learn` (RandomForest). PyTorch implementation is planned for future phases.

### Architecture

```
.NET App                          Python ML Service
┌──────────────────┐              ┌──────────────────┐
│ CustomMlAgent    │   HTTP/JSON  │ FastAPI          │
│ ModelClient      │ ──────────►  │ /predict         │
│ (X-API-Key)      │              │                  │
└──────────────────┘              └──────────────────┘
                                         │
                                         ▼
                                  ┌──────────────────┐
                                  │ TradingPredictor │
                                  │ (RSI, MACD, etc) │
                                  └──────────────────┘
```

## Commandes utiles

```bash
# Build & Test
dotnet restore && dotnet build
dotnet test AiTradingRace.Tests

# API
dotnet run --project AiTradingRace.Web

# Frontend
cd ai-trading-race-web && npm run dev

# Python ML Service
cd ai-trading-race-ml && uvicorn app.main:app --reload

# Azure Functions (local)
cd AiTradingRace.Functions && func start

# Docker SQL Server
docker start sqlserver
docker stop sqlserver

# Docker ML Service
cd ai-trading-race-ml && docker build -t ai-trading-ml .
docker run -p 8000:8000 ai-trading-ml
```

## Licence

Projet académique - École 2024-2026
