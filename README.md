# ai-trading-race


1. Concept du projet
Créer une “course” entre plusieurs IA de trading :
Chaque IA (GPT/Azure OpenAI, Claude, Grok, etc.) :
Analyse des données de marché crypto.
Prend des décisions d’investissement simulé (pas d’argent réel).

Un site web affiche :
L’évolution du capital de chaque IA (courbe argent / temps).
Un classement (qui gagne, qui perd).
L’historique des trades.

2. Fonctionnalités principales
Simulation de portefeuilles pour chaque agent IA.
Récupération automatique des prix crypto (BTC, ETH, etc.) via une API publique.
Agents IA qui tournent régulièrement :
Reçoivent l’historique de marché + leur portefeuille.
Décident : acheter / vendre / ne rien faire.

Calcul de :
PNL et valeur de portefeuille.
Courbe d’equity (valeur dans le temps).
Dashboard web :
Graphique comparant les IA.
Leaderboard (rendement en %, valeur totale).
Détails des trades par IA.
3. Stack technique (Azure + .NET)
Frontend
Blazor (Full .NET) pour le front :
Blazor Server ou Blazor WebAssembly.
UI avec un framework (MudBlazor par ex.) + un graph de courbes (Chart.js, etc.).
Pages :
Vue globale de la course.
Vue détaillée par agent (trades + courbe).
Backend / API
ASP.NET Core pour :
Exposer des endpoints REST (agents, trades, equity).
Gérer la logique métier (calculs de portefeuille, PNL).
Agents & Market Data
Azure Functions (.NET) :
Une function “MarketData” (timer) :
Appelle une API crypto (CoinGecko/Binance…).
Sauvegarde les prix / candles en base.
Une function “RunAgents” (timer ou queue) :
Charge les données de marché + portefeuilles.
Appelle les APIs LLM (Azure OpenAI, Claude, Grok…).
Parse la réponse (JSON) → trades structurés.
Met à jour la base (trades, positions, equity).
Base de données
Azure SQL Database + Entity Framework Core.
Tables typiques :
Agents (nom, type de modèle, provider).
MarketAssets (BTC, ETH, etc.).
MarketCandles (timestamp, open/high/low/close, volume).
Portfolios (capital de départ, IA associée).
Positions (quantités par actif).
Trades (achat/vente, quantité, prix, timestamp).
EquitySnapshots (valeur du portefeuille dans le temps).
Sécurité & config
Azure Key Vault pour stocker les clés d’API (LLM, market data).
Variables d’environnement pour les connexions (DB, etc.).
Déploiement & monitoring
Blazor + API : Azure App Service (Free ou petit plan).
Functions : Azure Functions (consumption plan).
CI/CD : GitHub Actions pour build & déploiement auto.
Logs & metrics : Azure Application Insights.

4. Objectifs

Faire du full-stack .NET (Blazor + ASP.NET Core).
Manipuler une base SQL avec EF Core et des données temporelles.
Intégrer des LLM multiples et les orchestrer.
Utiliser les services managés Azure (Functions, App Service, SQL, Key Vault, App Insights).
Mettre en place un système distribué avec jobs planifiés et simulation de trading.

5. Architecture solution .NET

Projets créés dans `AiTradingRace.sln` :

- `AiTradingRace.Web` : Blazor Server (UI + API future) avec DI configurée.
- `AiTradingRace.Domain` : entités métier (Agent, Portfolio, Trade, etc.).
- `AiTradingRace.Application` : modèles partagés + interfaces (`IMarketDataProvider`, `IPortfolioService`, `IAgentRunner`, `IAgentModelClient`).
- `AiTradingRace.Infrastructure` : implémentations mémoire et extension DI.
- `AiTradingRace.Functions` : Azure Functions isolé (.NET 8) avec timers `MarketDataFunction` et `RunAgentsFunction`.

Pré-requis locaux :

- .NET SDK 8.x (`https://dotnet.microsoft.com/en-us/download`).

Commandes utiles :

```bash
dotnet restore
dotnet build
dotnet run --project AiTradingRace.Web
func start --csharp --script-root AiTradingRace.Functions # si Azure Functions Core Tools est installé
# Base de données (Phase 2)
# 1) Installer l’outil EF si besoin : dotnet tool install --global dotnet-ef
# 2) Ajouter la chaîne de connexion `ConnectionStrings:TradingDb` dans :
#    - AiTradingRace.Web/appsettings.Development.json
#    - AiTradingRace.Functions/local.settings.json (ou secrets d’environnement)
# 3) Générer la migration initiale : dotnet ef migrations add InitialCreate -p AiTradingRace.Infrastructure -s AiTradingRace.Web
# 4) Appliquer la migration : dotnet ef database update -p AiTradingRace.Infrastructure -s AiTradingRace.Web
```