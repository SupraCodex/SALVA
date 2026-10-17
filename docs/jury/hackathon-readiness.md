# SALVA — Audit de préparation au hackathon

**État vérifié le 17 octobre 2026 — branche `feat/rebuild-salva-experience`**

Ce document distingue les éléments observés dans le dépôt des éléments seulement prévus dans le cahier des charges. Il ne transforme pas une intention ou un test local en preuve de livraison.

## Exigences officielles vérifiées

Les règles officielles de **Build With AI: Basics** exigent notamment :

- un projet créé pendant la période de soumission et construit avec le Devpost Learn Skill Pack ;
- un projet fonctionnel de bout en bout ;
- un dépôt public avec le code, les assets, les instructions et une licence open source ;
- les fichiers `scope.md`, `prd.md` et `spec.md` dans le dépôt ;
- une vidéo publique sur YouTube ou Vimeo, de moins de trois minutes, montrant le projet fonctionner ;
- une description et des instructions de test en anglais si les éléments soumis ne sont pas en anglais.

Source : <https://learn-ai-basics.devpost.com/rules>

## État réellement observé

| Point | État observé | Preuve ou manque |
|---|---|---|
| Dépôt public | OK | `SupraCodex/SALVA`, licence MIT à la racine |
| Documents du Skill Pack | Présents, mais `draft` | `devpost/scope.md`, `devpost/prd.md`, `devpost/spec.md` |
| Cahier des charges de l’équipe | Ajouté dans cette tranche | `docs/design/SALVA_Document_de_Conception_v1.0_2026-10-05.docx` |
| Code de l’application | Présent | `core/`, `backend/`, `frontend/`, `ml/`, `e2e/` |
| CI | Configurée | `.github/workflows/ci.yml` ; un fichier de workflow n’est pas la preuve d’un run vert sur le dernier commit |
| Tests frontend | Vérifiés localement | TypeScript, 13 tests et build passent sur cette branche |
| Tests core / ML / backend / E2E | Non déclarés ici comme vérifiés | Ils nécessitent leurs dépendances et, pour le backend/E2E, PostgreSQL et Playwright |
| Vidéo de démonstration | **MANQUANTE** | Aucun fichier vidéo dans le dépôt ; aucun lien public YouTube/Vimeo fourni |
| Application publique de test | Non démontrée dans cet audit | `docs/deployment.md` décrit un déploiement mais ne constitue pas une URL active |
| Validation terrain | **NON RÉALISÉE** | Le model card et le cahier la décrivent comme une étape à faire |
| Données réelles d’outcomes | Non démontrées | Le code collecte un résultat choisi, mais cela ne constitue pas une validation statistique |
| Traduction anglaise de la soumission | À préparer | L’interface est bilingue ; les éléments de soumission et la vidéo doivent également l’être |

## Écarts de périmètre à traiter avec prudence

Le cahier de conception v1.0 fixe la tomate comme seul produit correctement modélisé dans le MVP et place les autres produits en post-MVP. La branche de reprise ajoute des profils produits placeholders et les charge dans l’interface. Ces profils ne doivent pas être présentés comme calibrés ni validés. Une décision d’équipe doit documenter ce changement de périmètre avant toute promesse dans la soumission.

Le cahier définit aussi la validation terrain minimale, la répétition de la démo, la vidéo de secours et l’accessibilité de l’application comme des livrables de présentation. Ces points ne sont pas couverts par le seul fait que les suites de tests existent.

## Critères de sortie avant soumission

1. Les documents `scope.md`, `prd.md` et `spec.md` sont relus et leur statut est décidé par l’équipe.
2. Le parcours principal est exécuté sur une instance propre : création du lot, analyse, simulation, recommandation et suivi.
3. Les modes météo indisponible et LLM indisponible sont vérifiés sur l’instance réellement montrée.
4. Les tests exécutés sont listés avec leur commande, leur environnement et leur résultat ; aucun résultat supposé n’est présenté comme exécuté.
5. Une vidéo anglaise de moins de trois minutes montre l’application en fonctionnement, sans secret ni musique protégée.
6. Le lien vidéo est vérifié sans connexion et les instructions de test sont en anglais.
7. La soumission décrit explicitement que les chiffres sont basés sur un modèle et non validés sur données terrain.
8. Le cahier de conception, le script de démo et les limites sont versionnés dans le dépôt.

## Références

- Règles officielles : <https://learn-ai-basics.devpost.com/rules>
- Page du hackathon : <https://learn-ai-basics.devpost.com/>
- Ressources officielles : <https://learn-ai-basics.devpost.com/resources>
- Script de démonstration : [`docs/demo-script.md`](../demo-script.md)
- Model card : [`docs/model-card.md`](../model-card.md)
