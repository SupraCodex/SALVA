# ADR-006 — Catalogue produit extensible sans validation scientifique implicite

- **Statut :** proposé, à approuver par l’équipe
- **Date :** 17 octobre 2026

## Contexte

Le document de conception v1.0 fixe la tomate comme seul produit correctement modélisé dans le MVP et place les autres produits en post-MVP. La branche `feat/rebuild-salva-experience` introduit un catalogue produit dynamique et des profils supplémentaires explicitement décrits comme des placeholders à calibrer.

L’interface multi-produit est utile pour valider l’architecture et éviter de coder un écran entièrement figé sur la tomate. Elle crée cependant un risque de sur-promesse si un profil placeholder est présenté comme une prédiction validée.

## Décision proposée

Conserver le catalogue dynamique dans l’architecture, mais distinguer strictement :

1. la tomate, profil de référence du MVP et seul profil utilisé dans le scénario de soumission ;
2. les profils supplémentaires, profils de démonstration technique non calibrés, qui doivent afficher leur statut et ne doivent pas être présentés comme scientifiquement validés.

Aucun profil supplémentaire ne peut être promu comme profil de production sans paramètres sourcés, tests dédiés, fiche modèle et validation appropriée.

## Conséquences

- Le code peut tester l’extensibilité du catalogue sans modifier silencieusement la promesse scientifique du MVP.
- Le scénario vidéo reste centré sur la tomate, conformément au cahier des charges.
- La page Hypothèses doit rendre visible le statut du profil sélectionné.
- La soumission Devpost doit parler d’une architecture extensible, pas d’un modèle validé pour plusieurs produits.
- L’équipe doit approuver ou rejeter cette décision avant la fusion dans `main`.
