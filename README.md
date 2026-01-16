# ai-trading-race

Course entre agents IA de trading (LLM) qui pilotent chacun un portefeuille crypto simulé. Les prix de marché sont ingérés depuis CoinGecko, les agents décident (buy/sell/hold), et le dashboard React affiche l'equity et le classement.

## 📊 Statut du Projet

| Phase   | Description                            | Status      |
| ------- | -------------------------------------- | ----------- |
| Phase 1 | Architecture & Solution .NET           | ✅ Terminée |
| Phase 2 | Modèle de données & Base SQL           | ✅ Terminée |
| Phase 3 | Ingestion des données de marché        | ✅ Terminée |
| Phase 4 | Moteur de simulation (Portfolio & PnL) | 🔄 En cours |
| Phase 5 | Intégration agents IA                  | ⏳ À venir  |
| Phase 6 | Azure Functions (scheduler)            | ⏳ À venir  |
| Phase 7 | UI React Dashboard                     | 🔄 Partiel  |
| Phase 8 | Déploiement Azure                      | ⏳ À venir  |

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

- .NET 8 SDK
- Docker (pour SQL Server local)
- Node.js 18+ (pour le frontend React)
- Azure Functions Core Tools (optionnel)

## Démarrage rapide

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

## Tests

```bash
# Exécuter tous les tests
dotnet test

# Tests avec détails
dotnet test --verbosity normal
```

**Couverture actuelle (16 tests):**

- `CoinGeckoMarketDataClientTests` : Parsing JSON, erreurs HTTP, validation
- `MarketDataIngestionServiceTests` : Insertion, déduplication, gestion des assets

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

## Commandes utiles

```bash
# Build & Test
dotnet restore && dotnet build
dotnet test AiTradingRace.Tests

# API
dotnet run --project AiTradingRace.Web

# Frontend
cd ai-trading-race-web && npm run dev

# Azure Functions (local)
func start --csharp --script-root AiTradingRace.Functions

# Docker SQL Server
docker start sqlserver
docker stop sqlserver
```

## Licence

Projet académique - École 2024-2026
