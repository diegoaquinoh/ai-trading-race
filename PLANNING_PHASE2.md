## Phase 2 – Modèle de données & base SQL

**Objectif :** définir et persister tous les objets métier (agents, actifs, candles, portefeuilles, positions, trades, equity) sur une base SQL prête pour la suite.

**État actuel (07/12/2025) — audit rapide :**
- Fondations EF livrées : `TradingDbContext` + contraintes, seeds BTC/ETH et agents, bougies initiales.
- Services persistants EF en place : `EfMarketDataProvider`, `EfPortfolioService` (portefeuille par agent, trades, snapshots).
- DI configurée SQL Server avec fallback in-memory ; Web et Functions passent la configuration.
- Reste à faire côté dev : générer/appliquer la première migration et alimenter de vraies données de marché.

**Hypothèses / décisions à valider :**
- Base : Azure SQL / SQL Server (EF Core), timezone UTC, décimales avec précision (18,8) pour prix/quantités.
- Stratégie secrets : `appsettings.Development.json` + `dotnet user-secrets` pour la chaîne de connexion locale.
- Seed minimal : actifs BTC/ETH, 2–3 agents de démo (GPT, Claude, Grok).

**Backlog priorisé (Phase 2) :**
- P0 – Schéma & fondations EF Core (bloquant)  
  - Créer `TradingDbContext` + configurations fluent pour toutes les entités (tables, clés, index uniques sur `MarketAsset.Symbol`, FK, contraintes basiques prix/volume > 0).  
  - Ajouter la connexion dev (`appsettings.Development.json` + secrets) et enregistrer le `DbContext` dans Web + Functions.  
  - Générer la migration initiale + script SQL ; vérifier la création locale.  
  - Seed minimal : `MarketAsset` (BTC, ETH) + quelques `Agent` de démonstration.
- P1 – Services persistants  
  - Implémenter `EfMarketDataProvider` : stockage / lecture des `MarketCandle` avec dé-duplication (clé composite asset/timestamp).  
  - Implémenter `EfPortfolioService` : création portefeuille par agent, application de trades (achat/vente), recalcul positions et snapshots d’equity, transactions atomiques.  
  - Tests d’intégration (SQLite in-memory ou LocalDB) couvrant : seed, ingestion candle, achat/vente, PnL +/-.
- P2 – Opérations & DX  
  - Documenter les commandes (`dotnet ef migrations add InitialCreate`, `dotnet ef database update`) et la configuration des secrets.  
  - Ajouter quelques garde-fous : timestamps en UTC, précisions décimales cohérentes, logs basiques sur l’ingestion et les trades.

**Mise en œuvre (07/12/2025) :**
- `TradingDbContext` ajouté avec contraintes (index uniques, check, décimales 18,8) + seeds BTC/ETH et agents GPT/Claude/Grok, première bougie par actif.
- Services persistants EF : `EfMarketDataProvider` et `EfPortfolioService` (portefeuille par agent, trades, snapshots d’equity, transactions) enregistrés via DI.
- DI configurée pour utiliser SQL Server si `ConnectionStrings:TradingDb` est présent, sinon fallback base en mémoire ; Web et Functions passent la configuration.
- Fichiers de config mis à jour (`appsettings.Development.json`, `local.settings.json.example`) et README documente les commandes EF (`migrations add`, `database update`). Migration initiale à générer/appliquer côté dev.

**Critères de sortie :**
- La migration initiale crée toutes les tables et s’applique en local.  
- Les seeds insèrent au moins BTC/ETH et des agents de démonstration.  
- Les services DI utilisent EF Core en dev (in-memory possible en fallback explicite).  
- Les tests d’intégration passent sur le modèle de données et les services persistants.

