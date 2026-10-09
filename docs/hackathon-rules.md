# Build With AI: Basics — règles vérifiées

Source officielle : <https://learn-ai-basics.devpost.com/rules> (consultée le 9 octobre 2026).

## Contraintes qui affectent SALVA

- Le projet doit être nouveau pendant la période de soumission et construit avec le Devpost Learn Skill Pack.
- Le dépôt de soumission doit être **public**, contenir le code, les instructions d’installation, les assets nécessaires et une licence open source détectable.
- Le dépôt doit contenir les documents générés par le Skill Pack : `scope.md`, `prd.md` et `spec.md`.
- Le projet doit être un proof of concept fonctionnel de bout en bout, créé pendant la période de soumission; tout code ou travail préexistant incorporé doit être divulgué.
- Le premier stade de jugement vérifie l’adéquation au thème et l’usage du Skill Pack, attesté par les documents de planification du dépôt.
- Le projet doit fonctionner de bout en bout sur sa plateforme cible et fonctionner comme montré dans la vidéo et la description.
- La vidéo de démonstration doit être publique sur YouTube ou Vimeo et durer moins de trois minutes.
- Si la soumission n’est pas en anglais, il faut fournir une traduction anglaise de la vidéo, de la description, des instructions de test et de tous les autres éléments soumis.
- Le projet doit être original, détenu par l’équipe, et les intégrations tierces doivent être utilisées conformément à leurs licences.
- Le projet doit rester disponible gratuitement pour les tests et l’évaluation pendant la période de jugement.
- Le second stade pondère également quatre critères : design, impact potentiel, innovation/idéation et présentation.
- La période d’inscription et de soumission se termine le 26 octobre 2026 à 17 h, heure de l’Est.

## Conséquence pour cette branche

`core/` reste une bibliothèque scientifique Python pure et ne prétend pas satisfaire seul les
exigences de soumission au niveau projet. Les fichiers Devpost, la vidéo, la licence globale,
l’intégration backend/frontend et la démonstration doivent être vérifiés et finalisés par
l’équipe d’intégration. Cette séparation évite de fabriquer dans core des artefacts de hackathon
qui ne seraient pas la source de vérité du produit.

Le dépôt officiel `challengepost/learn-ai-basics` décrit les sorties de compétences sous
`devpost/` (`scope.md`, `prd.md`, `spec.md`) et précise que la soumission et les réponses au
questionnaire de sortie sont rédigées par les participants. Cette branche ne crée aucun de ces
documents et ne les présente pas comme achevés.
