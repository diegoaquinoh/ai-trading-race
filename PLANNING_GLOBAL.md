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

## Phase 7 – UI React : dashboard & détail agent

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

---

## Phase 8 – Déploiement Azure & configuration prod

**Objectif :** rendre le projet accessible en ligne et proprement configuré.

**Tâches :**

- Créer les ressources Azure :

  - Azure SQL Database.
  - App Service pour `AiTradingRace.Web`.
  - Azure Functions (hébergement consumption).
  - Azure Key Vault (clés API LLM, chaînes de connexion).

- Ajouter les connexions ET secrets :

  - Chaîne de connexion SQL dans App Service / Functions via Key Vault ou config.
  - Clés d’API LLM dans Key Vault.

- Mettre en place le déploiement :

  - Build & publish depuis GitHub (GitHub Actions) vers :

    - App Service.
    - Functions.

- Configurer les migrations de BD au démarrage (ou script SQL dédié).

**Critère de sortie :** l’application est accessible via une URL Azure, les Functions tournent, les données sont stockées dans Azure SQL.

> **Note Phase 5 :** Les clés API LLM (GitHub Models, OpenAI, Azure OpenAI) seront configurées ici. Modifier `Program.cs` pour utiliser `AddInfrastructureServices()` au lieu de `AddInfrastructureServicesWithTestAI()`.

---

## Phase 9 – Monitoring, sécurité minimale & polish CV

**Objectif :** rendre le projet “propre” aux yeux d’un recruteur.

**Tâches :**

- Activer Application Insights sur :

  - App Service.
  - Azure Functions.

- Ajouter des logs côté code :

  - Exécution des agents (agent, temps de réponse, erreurs).
  - Appels aux APIs externes (succès / échecs).

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
