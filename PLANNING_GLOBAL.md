Parfait, on passe en mode “chef de projet dev” 👷‍♂️📋
Voici un planning de tâches structuré, sans parler de durée, mais dans **un ordre professionnel** que tu peux suivre comme backlog.

---


**Critère de sortie :** tu as un README et un backlog clair dans des issues GitHub ou un board Kanban.

---

## Phase 1 – Architecture & solution .NET

**Objectif :** poser la base technique du projet.

**Tâches :**

* Créer la solution `.NET` avec les projets suivants :

  * `AiTradingRace.Web` → Blazor Server (UI + API).
  * `AiTradingRace.Domain` → entités métier (Agent, Trade, Portfolio…).
  * `AiTradingRace.Application` → services métier, interfaces (use cases).
  * `AiTradingRace.Infrastructure` → EF Core, accès BD, appel APIs externes.
  * `AiTradingRace.Functions` → Azure Functions (market data, agents).
* Configurer l’injection de dépendances (DI) :

  * Enregistrer les services de domaine / application dans `Web` et `Functions`.
* Définir les interfaces principales dans `Application` :

  * `IMarketDataProvider`
  * `IPortfolioService`
  * `IAgentRunner`
  * `IAgentModelClient` (abstraction sur les LLM).

**Critère de sortie :** la solution compile, les projets se voient entre eux, DI en place.

---

## Phase 2 – Modèle de données & base SQL

**Objectif :** définir et persister tous les objets métier.

**État actuel (07/12/2025) :** fondations EF livrées (`TradingDbContext`, contraintes, seeds BTC/ETH + agents, premières bougies). Services persistants EF (`EfMarketDataProvider`, `EfPortfolioService`) enregistrés en DI avec fallback in-memory si pas de `ConnectionStrings:TradingDb`. Web/Functions câblés sur la config. Migration initiale à générer/appliquer côté dev.

**Tâches prioritaires (restant à faire) :**

* P0 – Finaliser schéma
  * Générer la migration initiale + script SQL ; vérifier la création locale.
* P1 – Services persistants
  * Ajouter tests d’intégration (SQLite in-memory ou LocalDB) pour seed, ingestion candle, PnL +/-.
* P2 – Opérations
  * Documenter/automatiser la gestion des secrets (user-secrets, Key Vault) et ajouter logs ingestion/trades.

**Critère de sortie :** la BD se crée depuis les migrations, contient les seeds de base, et les services DI utilisent EF Core en dev (in-memory en fallback explicite).

---

## Phase 3 – Ingestion des données de marché

**Objectif :** stocker des prix crypto en base.

**Tâches :**

* Dans `Application` :

  * Définir un service `IMarketDataProvider` (signature propre).
* Dans `Infrastructure` :

  * Implémenter un `CoinGeckoMarketDataProvider` (ou Binance, peu importe).
  * Gérer :

    * Récupération des chandeliers (OHLC).
    * Mapping JSON → `MarketCandle`.
    * Persistance via `TradingDbContext`.
* Exposer un service `MarketDataIngestionService` qui :

  * Récupère les derniers prix.
  * Évite les doublons de candles.
* Créer un petit endpoint ou page admin pour lancer l’ingestion manuellement (utile avant d’avoir les Functions).

**Critère de sortie :** tu peux déclencher l’ingestion et voir des `MarketCandles` en base pour BTC/ETH.

---

## Phase 4 – Moteur de simulation (portefeuille & PnL)

**Objectif :** être capable de simuler des trades et d’actualiser la valeur d’un portefeuille.

**Tâches :**

* Dans `Application` :

  * Créer `IPortfolioService` :

    * Créer un portfolio pour un agent.
    * Appliquer un trade (achat/vente).
    * Recalculer les positions.
    * Calculer la valeur du portefeuille à partir des derniers prix.
  * Créer `IEquityService` :

    * Générer un `EquitySnapshot` à partir du portefeuille + prix.
* Dans `Infrastructure` :

  * Implémentations concrètes de ces services avec EF Core.
* Ajouter quelques tests unitaires (même simples) :

  * Cas de base : achat, vente, PnL positif, PnL négatif.
* Ajouter un endpoint API :

  * `GET /api/agents/{id}/equity` → renvoie la courbe d’equity (pour la future UI).

**Critère de sortie :** en insérant quelques trades à la main, tu vois la valeur du portefeuille évoluer et des snapshots se créer.

---

## Phase 5 – Intégration d’un premier agent IA

**Objectif :** brancher un premier LLM et obtenir des décisions de trading.

**Tâches :**

* Dans `Application` :

  * Définir un `AgentContext` (historique de prix, positions, cash).
  * Définir un `AgentDecision` (liste d’ordres normalisés).
  * Créer `IAgentModelClient` (interface pour interroger un modèle).
* Dans `Infrastructure` :

  * Implémenter `AzureOpenAiAgentModelClient` (ou autre provider que tu as).
  * Construire le prompt :

    * Règles (pas de levier, risque max, format JSON, etc.).
    * Contexte (quelques candles, positions, cash).
  * Parser la réponse en `AgentDecision` (JSON → C#).
* Dans `Application` :

  * Créer un `AgentRunner` :

    * Charge le contexte.
    * Appelle `IAgentModelClient`.
    * Valide et applique les trades via `IPortfolioService`.
    * Crée un `EquitySnapshot`.
* Ajouter un endpoint ou une commande interne :

  * Permet de lancer l’agent pour un cycle (ex. `RunAgentOnce(agentId)`).

**Critère de sortie :** tu peux déclencher un “tour” pour un agent, tu vois des trades générés par l’IA et la courbe d’equity se mettre à jour.

---

## Phase 6 – Azure Functions (scheduler & automatisation)

**Objectif :** automatiser ingestion de marché + exécution des agents.

**Tâches :**

* Projet `AiTradingRace.Functions` :

  * Function timer `MarketDataFunction` :

    * Appelle `MarketDataIngestionService`.
  * Function timer `RunAgentsFunction` :

    * Liste tous les agents actifs.
    * Appelle `AgentRunner` pour chacun.
* (Optionnel plus avancé) :

  * Utiliser Azure Queue / Service Bus :

    * `RunAgentsFunction` envoie un message par agent.
    * Une Function queue-trigger traite chaque message (scalabilité).
* Configurer les `appsettings` / `local.settings.json` pour liaison BD, APIs externes.
* Tester les Functions en local (Azurite ou direct sur ton compte Azure).

**Critère de sortie :** les cycles “fetch market data” + “run all agents” peuvent tourner automatiquement via Functions.

---

## Phase 7 – UI Blazor : dashboard & détail agent

**Objectif :** afficher visuellement la “course” entre les IA.

**Tâches :**

* Structure Blazor :

  * Layout (sidebar/topbar).
  * Pages :

    * `/` → dashboard global.
    * `/agents` → liste des agents.
    * `/agents/{id}` → détail d’un agent.
* Dashboard global :

  * Appel à l’API pour récupérer :

    * La liste des agents.
    * La courbe d’equity de chaque agent (échantillonnée).
  * Intégration d’un composant de graphique (via MudBlazor, Chart.js, etc.).
  * Tableau leaderboard :

    * Nom agent, valeur actuelle, % de performance, drawdown éventuel.
* Page détail agent :

  * Mini graphique d’equity.
  * Tableau des trades récents.
  * Informations (stratégie, provider LLM, paramètres).
* Ajout de composants de chargement / erreurs (UX propre).

**Critère de sortie :** en ouvrant l’app, tu vois la course sous forme de graph, tu peux cliquer sur un agent pour voir son historique.

---

## Phase 8 – Déploiement Azure & configuration prod

**Objectif :** rendre le projet accessible en ligne et proprement configuré.

**Tâches :**

* Créer les ressources Azure :

  * Azure SQL Database.
  * App Service pour `AiTradingRace.Web`.
  * Azure Functions (hébergement consumption).
  * Azure Key Vault (clés API LLM, chaînes de connexion).
* Ajouter les connexions ET secrets :

  * Chaîne de connexion SQL dans App Service / Functions via Key Vault ou config.
  * Clés d’API LLM dans Key Vault.
* Mettre en place le déploiement :

  * Build & publish depuis GitHub (GitHub Actions) vers :

    * App Service.
    * Functions.
* Configurer les migrations de BD au démarrage (ou script SQL dédié).

**Critère de sortie :** l’application est accessible via une URL Azure, les Functions tournent, les données sont stockées dans Azure SQL.

---

## Phase 9 – Monitoring, sécurité minimale & polish CV

**Objectif :** rendre le projet “propre” aux yeux d’un recruteur.

**Tâches :**

* Activer Application Insights sur :

  * App Service.
  * Azure Functions.
* Ajouter des logs côté code :

  * Exécution des agents (agent, temps de réponse, erreurs).
  * Appels aux APIs externes (succès / échecs).
* Gérer les erreurs UI :

  * Messages d’erreur clairs en cas de problème API.
  * Gestion des états “pas de data”.
* Documentation :

  * Compléter le `README.md` :

    * Description du projet.
    * Architecture (schéma texte ou image).
    * Stack technique détaillée.
    * Instructions pour lancer en local.
    * Lien vers la version déployée.
