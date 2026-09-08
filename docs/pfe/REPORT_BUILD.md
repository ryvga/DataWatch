# Rapport PFE, reconstruction et contrôle

Le document maître est `output/pfe/Rapport_PFE_Panopta_Mounir_Gaiby.docx`. Le PDF exporté porte le même nom dans le même dossier.

Une édition compacte est également livrée dans `output/pfe/Rapport_PFE_Panopta_Mounir_Gaiby_Compact.docx` et `output/pfe/Rapport_PFE_Panopta_Mounir_Gaiby_Compact.pdf`. Elle conserve le même contenu, les 44 figures et la structure ISGA. Sa mise en page plus dense réduit le document actuel de 74 à 57 pages sans supprimer les preuves utiles à la soutenance.

Le guide remis par l’encadrant est conservé dans `docs/pfe/reference/Structure_Rapport_ISGA.pdf`. Le générateur vérifie sa présence et son empreinte SHA-256 avant chaque construction. Si le fichier change, il interrompt la génération. La nouvelle version doit alors être relue et le rapport revalidé avant toute mise à jour de l’empreinte.

## Sources institutionnelles et professionnelles

- `docs/pfe/assets/isga-logo.png`, logo ISGA utilisé sur la couverture.
- `docs/pfe/assets/oyster-logo-black.png`, logo officiel Oyster utilisé sur la couverture et dans le chapitre de présentation.
- `docs/pfe/report_source.json`, contenu éditorial de base.
- `docs/pfe/database_evidence.json`, preuve structurée du modèle de données et du jeu seedé.
- `docs/diagrams/pfe/`, diagrammes et sources Mermaid.
- `docs/screenshots/pfe/`, captures du produit seedé.

Le rapport présente Oyster comme l’employeur de Mounir Gaiby. Son poste est Software Engineer dans l’équipe Payments. Le PFE n’est pas un stage. Panopta reste un projet académique distinct et ne doit jamais être présenté comme un produit Oyster ou comme une reproduction de systèmes internes.

## 1. Préparer les preuves

```bash
docker compose up -d --wait
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
python scripts/pfe/export_database_evidence.py
python scripts/pfe/generate_report_visuals.py
cd frontend
npm run capture:pfe
cd ..
```

L’export décrit les 29 tables SQLAlchemy, leurs relations et des exemples seedés non sensibles. Le Gantt couvre le 1er juin au 31 août 2026. La continuité du produit après la période académique reste visible.

## 2. Construire le Word

```bash
/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/pfe/build_rapport_word.py
```

Pour construire l’édition compacte sans écraser le document maître :

```bash
/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/pfe/build_rapport_word.py --compact
```

Sur une autre machine, utiliser Python avec `python-docx`, `Pillow` et `lxml`. LibreOffice et Poppler sont nécessaires au contrôle PDF et à la stabilisation des numéros de page.

## 3. Stabiliser les index

Le générateur insère un vrai champ Word pour la table des matières et des liens internes pour les index visibles. Les numéros imprimés sont stabilisés en deux passes.

1. Générer le DOCX.
2. Le rendre en PDF.
3. Extraire la page de chaque titre, figure et tableau dans `tmp/pfe/report-page-map.json`.
4. Reconstruire puis rendre une seconde fois.

L’édition compacte utilise `tmp/pfe/report-page-map-compact.json` afin de conserver ses propres numéros de page.

Commande d’extraction :

```bash
python scripts/pfe/extract_report_page_map.py \
  output/pfe/Rapport_PFE_Panopta_Mounir_Gaiby.docx \
  tmp/pfe/rendered-report/Rapport_PFE_Panopta_Mounir_Gaiby.pdf \
  tmp/pfe/report-page-map.json
```

Dans Microsoft Word, sélectionner tout puis actualiser les champs avant le dépôt final afin que le lecteur natif recalcule également la table des matières.

## 4. Contrat documentaire attendu

- Couverture A4 avec les logos ISGA et Oyster, le titre, le diplôme, la filière, le nom de l’étudiant, le nom de l’encadrant, l’entreprise et l’année universitaire.
- Dédicace, remerciements, résumé, abstract, table des matières et listes en chiffres romains.
- Corps en chiffres arabes à partir de l’introduction générale.
- Ordre conforme au guide ISGA, avec introduction et conclusion pour chaque chapitre.
- Présentation propre d’Oyster, de l’équipe Payments et du poste occupé.
- 44 figures, avec un Gantt, 19 vues de contexte et de conception, puis 24 captures réelles.
- Chaque figure est annoncée, légendée et interprétée.
- Aucun secret, jeton, identifiant personnel ou chaîne de connexion dans les annexes ou captures.
- Aucun tiret cadratin, tiret demi-cadratin ou point-virgule dans le texte produit.
- Inspection visuelle de chaque page, audit d’accessibilité et vérification des liens avant livraison.
