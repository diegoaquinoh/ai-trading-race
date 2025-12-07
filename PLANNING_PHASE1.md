# Planning Phase 1 – Architecture & solution .NET

## Contexte
Phase 1 doit poser la fondation technique du projet `ai-trading-race`. L’objectif est de créer une solution .NET modulaire couvrant l’UI (Blazor Server), la logique métier, l’accès aux données et les futures Azure Functions. Cette phase est terminée lorsque la solution compile, que les projets se référencent correctement et que l’injection de dépendances (DI) relie les différentes couches.

## Objectifs principaux
- Initialiser la solution `.NET` complète.
- Définir clairement les frontières entre `Web`, `Domain`, `Application`, `Infrastructure`, `Functions`.
- Mettre en place la DI et les interfaces clés (`IMarketDataProvider`, `IPortfolioService`, `IAgentRunner`, `IAgentModelClient`).
- Garantir que la solution compile et que les projets se voient mutuellement selon l’architecture cible.

## Livrables attendus
- Solution `.sln` avec les cinq projets créés et référencés.
- Configuration DI de base dans `AiTradingRace.Web` et `AiTradingRace.Functions`.
- Interfaces principales définies dans `AiTradingRace.Application`.
- Documentation minimale (README ou commentaire) décrivant l’architecture et les projets.

## Hypothèses & dépendances
- SDK .NET 8 installé (ou version alignée avec l’équipe).
- Aucun besoin immédiat de base de données opérationnelle (introduite en Phase 2).
- Gestion des secrets/API différée aux phases ultérieures.

## Découpage des travaux

| # | Bloc de travail | Description | Entrées | Sorties |
|---|-----------------|-------------|---------|---------|
| 1 | Initialisation solution | Créer la solution `.sln` et les projets listés dans `PLANNING_GLOBAL`. Utiliser les gabarits adéquats (`blazorserver`, `classlib`, `azfunc`). | README global, besoins d’architecture. | Solution .NET avec projets présents. |
| 2 | Références croisées | Ajouter les références projet nécessaires (`Web` → `Application` & `Infrastructure`, etc.). Vérifier que chaque couche n’accède qu’aux couches autorisées. | Solution créée. | Couches liées, build réussi. |
| 3 | Configuration DI | Dans `Web` et `Functions`, enregistrer les services des couches Domain/Application/Infrastructure. Préparer des méthodes d’extension pour simplifier l’enregistrement. | Projet Application avec services vides. | Services enregistrés, démarrage de l’host réussi. |
| 4 | Interfaces métier | Définir dans `AiTradingRace.Application` les interfaces `IMarketDataProvider`, `IPortfolioService`, `IAgentRunner`, `IAgentModelClient`, plus les modèles de données partagés. | Lecture des besoins fonctionnels (README). | Interfaces signées, prêtes pour implémentation. |
| 5 | Validation & documentation | Compiler la solution, exécuter un run basique du projet Web. Documenter brièvement l’architecture (README ou doc dédié). | Build/Run locaux. | Build vert + documentation résumant Phase 1. |

## Critères de sortie
- `dotnet build` réussit pour toute la solution.
- Les projets sont organisés selon l’architecture hexagonale visée.
- La DI permet d’instancier les services clés sans implémentations concrètes (stubs autorisés).
- README ou planning mis à jour pour refléter l’état de l’architecture.

## Plan de tests rapide
- Build complet de la solution.
- Lancement de `AiTradingRace.Web` (même si aucune page métier n’est encore développée) pour vérifier la configuration DI.
- Tests unitaires éventuels de compilation pour les interfaces (ex. projets de tests vides préparés).

## Suivi & prochaines étapes
- Identifier les gaps restants (ex. modèles domaine manquants) avant d’entamer la Phase 2.
- Préparer les scripts/commandes pour créer les migrations lors de la prochaine phase.
- Tenir un journal de bord rapide indiquant : date de création solution, références ajoutées, éventuelles décisions techniques.

