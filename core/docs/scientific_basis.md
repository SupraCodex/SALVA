# Base scientifique et limites du moteur de perte

Ce document sépare les effets post-récolte étayés par la littérature des coefficients numériques encore supposés dans SALVA. La recherche confirme que la température, la maturité et la variabilité génétique influencent l’évolution post-récolte de la tomate. Elle ne fournit pas, à elle seule, des coefficients universels permettant de convertir ces effets en perte de valeur commerciale pour les lots SALVA.

## Ce que les sources étayent

Thole et al. ont suivi plus de 1 800 fruits issus de 41 accessions à 18 °C et 26 °C. Dans cet ensemble, la durée de conservation diminuait en moyenne d’environ 11 % à température élevée, mais les réponses variaient sensiblement entre accessions : certaines étaient peu affectées, d’autres plus sensibles. Cette étude confirme que la chaleur compte, mais invalide l’idée d’un effet numérique uniforme transférable à n’importe quel cultivar, maturité ou chaîne logistique [1].

Ciptaningtyas et al. ont modélisé l’évolution de la couleur des tomates vertes matures pour trois cultivars à températures de stockage constantes entre 12 et 30 °C. Le modèle ajuste le changement de couleur dans ses conditions expérimentales; les auteurs signalent que son développement ne couvre pas encore les températures dynamiques d’une chaîne de distribution. La couleur et le temps de mûrissement ne sont pas équivalents à la fraction de valeur économique modélisée par SALVA [2].

David et al. montrent une variabilité génétique marquée de la tolérance au froid dans une population de 148 lignées de tomate soumises à 1,5 °C. Ce résultat étaye la prudence face à un seuil de blessure au froid unique, mais l’expérience ne calibre pas une fonction universelle de perte ni les seuils par cultivar utilisés dans SALVA [3].

## Interprétation des coefficients de SALVA

Le moteur implémente une fonction cinétique Q10, une variabilité log-normale de lot, des pertes par emballage et déclassement, une pénalité de froid et des seuils de risque configurables. Ces mécanismes sont transparents et testables. Les coefficients de `data/reference/products.yaml` qui portent `source: assumption` — notamment `k_ref`, `q10`, les dispersions, dommages d’emballage, hypothèses économiques et les paramètres de dose de froid — restent des valeurs initiales de planification, pas des ajustements expérimentaux à un cultivar camerounais.

Les paramètres de froid sourcés dans la littérature sont des repères de conduite post-récolte, pas une loi dose-réponse universelle. En particulier, la vitesse de la pénalité économique de froid et la conversion en perte commerciale de SALVA ne sont pas mesurées par les études citées. La durée de vie restante est donc une projection conditionnelle aux paramètres et à la température historique approximative fournie, pas une garantie de salubrité ni une date d’expiration.

Les études publiées n’ont pas la même variable cible que le moteur (couleur, durée avant surmaturité, dommages physiologiques ou qualité mesurée), ni les mêmes cultivars, maturités, humidités, emballages et profils de température. Il serait scientifiquement incorrect de réajuster `k_ref`, `q10`, `sigma_lot` ou le taux de dommage au froid en prenant un seul chiffre de ces travaux. Une calibration défendable exige des lots identifiés par cultivar et stade, des historiques de température et des mesures économiques/qualité alignées sur les sorties SALVA, puis une validation sur des lots distincts.

## Ce que l’analyse de sensibilité permet

`relative_hypothesis_parameter_paths(params, model=model)` fournit les paramètres produit déclarés `assumption` dont les deux scénarios relatifs restent non nuls, dans le domaine physique ou métier, et que l’adaptateur fourni peut effectivement appliquer. Sans modèle, elle retourne les candidats au niveau produit. Les paramètres issus de la littérature et les bases nulles ne sont pas proposés comme perturbations relatives. `analyze_parameter_sensitivity` recalcule les pertes, valeurs et recommandations sous les mêmes chocs; les niveaux de risque de chaque scénario sont également retournés pour rendre visibles les changements de seuil RM-5.

Cette analyse explore la dépendance de la décision aux hypothèses. Elle ne transforme pas ces hypothèses en paramètres calibrés, ne retrain pas les boosters LightGBM et ne remplace pas la validation hors échantillon.

L’adaptateur de perte déclare les chemins de sensibilité qu’il sait effectivement appliquer. Le modèle cinétique de référence en accepte tous les paramètres produit configurés. LightGBM n’accepte que les paramètres connectés à ses features, à sa projection de durée de vie ou à sa pénalité commune de froid; une variation cinétique/grading sans chemin dans les boosters figés échoue explicitement au lieu d’être présentée comme une mesure d’impact nulle.

## Références

[1]: https://pmc.ncbi.nlm.nih.gov/articles/PMC8623658/ "Effect of Elevated Temperature on Tomato Post-Harvest Properties (Thole et al., 2021)"
[2]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9114344/ "Modeling the metachronous ripening pattern of mature green tomato as affected by cultivar and storage temperature (Ciptaningtyas et al., 2022)"
[3]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9493348/ "Physiological genetic variation in tomato fruit chilling tolerance during postharvest storage (David et al., 2022)"
