# ai-trading-race

Course entre agents IA de trading (LLM) qui pilotent chacun un portefeuille crypto simulé. Les prix de marché sont ingérés, les agents décident (buy/sell/hold), et le dashboard Blazor affiche l’equity et le classement.

## Architecture
- `AiTradingRace.Web` : Blazor Server (UI + API future), DI configurée.
- `AiTradingRace.Domain` : entités métier (Agents, Assets, Candles, Portfolios, Positions, Trades, EquitySnapshots).
- `AiTradingRace.Application` : contrats partagés (`IMarketDataProvider`, `IPortfolioService`, `IAgentRunner`, `IAgentModelClient`).
- `AiTradingRace.Infrastructure` : implémentations EF Core (SQL Server + fallback in-memory), agents/market data/portefeuilles, factory design-time.
- `AiTradingRace.Functions` : Azure Functions isolé (.NET 8) avec timers `MarketDataFunction` et `RunAgentsFunction`.



## Prérequis
- .NET 8 SDK
- Azure Functions Core Tools (optionnel pour exécuter les Functions)
- Docker (pour SQL Server local) ou un SQL Server existant

## Démarrage rapide
```bash
dotnet restore
dotnet build
dotnet run --project AiTradingRace.Web              # utilise SQL si présent, sinon in-memory
func start --csharp --script-root AiTradingRace.Functions  # nécessite la chaîne SQL
```

## Base de données (dev SQL Server)
1) Lancer un SQL Server local (exemple Docker) :
```bash
docker run -d --name sqltrading \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=<votre_mot_de_passe_fort>" \
  -p 1433:1433 mcr.microsoft.com/mssql/server:2022-latest
```
2) Définir la chaîne de connexion (Web) via secrets user :
```bash
dotnet user-secrets set "ConnectionStrings:TradingDb" "Server=localhost,1433;Database=AiTradingRace;User Id=sa;Password=<votre_mot_de_passe_fort>;TrustServerCertificate=True;" --project AiTradingRace.Web
```
3) Pour l’EF CLI, exporter la même chaîne avant les commandes :
```bash
export ConnectionStrings__TradingDb="Server=localhost,1433;Database=AiTradingRace;User Id=sa;Password=<votre_mot_de_passe_fort>;TrustServerCertificate=True;"
```
4) Appliquer la migration initiale :
```bash
dotnet ef database update -p AiTradingRace.Infrastructure -s AiTradingRace.Web
```
5) Exemple Functions : copier `AiTradingRace.Functions/local.settings.json.example` en `local.settings.json` et y placer la même chaîne dans `ConnectionStrings:TradingDb`.

Sans chaîne définie, l’appli Web tombe en base in-memory (données éphémères).

## Migrations EF
- Ajouter : `dotnet ef migrations add <Name> -p AiTradingRace.Infrastructure -s AiTradingRace.Web`
- Mettre à jour : `dotnet ef database update -p AiTradingRace.Infrastructure -s AiTradingRace.Web`
- La factory design-time lit `ConnectionStrings__TradingDb`; à défaut, fallback SQLite (fichier `design.db`) pour générer la migration.

## Fonctionnalités visées
- Simulation de portefeuilles multi-agents avec PnL et courbe d’equity.
- Leaderboard et détails de trades sur le dashboard Blazor.
- Jobs planifiés : ingestion de marché (`MarketDataFunction`) puis appel des agents (`RunAgentsFunction`) pour générer des ordres structurés.
- Intégrations LLM multiples (Azure OpenAI, Claude, Grok) orchestrées via les interfaces Application.

## Commandes utiles
- Restaurer/build : `dotnet restore && dotnet build`
- Lancer le front : `dotnet run --project AiTradingRace.Web`
- Lancer les Functions : `func start --csharp --script-root AiTradingRace.Functions`
- Outil EF (si besoin) : `dotnet tool install --global dotnet-ef`