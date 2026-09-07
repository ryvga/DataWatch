# Rapport PFE — reconstruction et contrôle

Le document maître est `output/pfe/Rapport_PFE_DataWatch_Mounir_Gaiby.docx`. Il est généré depuis le contenu éditorial, les preuves de base de données, les diagrammes reproductibles et les captures de l’application seedée.

## 1. Préparer les preuves

```bash
docker compose up -d --wait
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
python scripts/pfe/export_database_evidence.py
python scripts/pfe/generate_report_visuals.py
cd frontend && npm run capture:pfe
cd ..
```

L’export décrit les 29 tables SQLAlchemy, leurs colonnes, contraintes et relations, puis ajoute uniquement des exemples seedés non sensibles. Le générateur visuel conserve les sources Mermaid dans `docs/diagrams/pfe/mermaid/`. Le Gantt couvre le 1er juin au 31 août 2026 et distingue la poursuite du produit après la période académique.

## 2. Construire le Word

```bash
/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/pfe/build_rapport_word.py
```

Sur une autre machine, utiliser Python avec `python-docx`, `Pillow` et `lxml`. LibreOffice et Poppler sont nécessaires au contrôle PDF et à la stabilisation des numéros de page.

## 3. Stabiliser les index

Le générateur insère un vrai champ Word pour la table des matières et des liens internes pour les index visibles. Les numéros imprimés sont stabilisés en deux passes :

1. générer le DOCX ;
2. le rendre en PDF ;
3. extraire la page de chaque titre, figure et tableau dans `tmp/pfe/report-page-map.json` ;
4. reconstruire puis rendre une seconde fois.

Commande d’extraction :

```bash
python scripts/pfe/extract_report_page_map.py \
  output/pfe/Rapport_PFE_DataWatch_Mounir_Gaiby.docx \
  tmp/pfe/rendered-report/Rapport_PFE_DataWatch_Mounir_Gaiby.pdf \
  tmp/pfe/report-page-map.json
```

Dans Microsoft Word, sélectionner tout puis actualiser les champs avant le dépôt final afin que le lecteur natif recalcule également la table des matières.

## 4. Contrat documentaire attendu

- A4, couverture ISGA sans numéro et sans page blanche parasite ;
- préliminaires numérotés en chiffres romains ; corps en chiffres arabes à partir de l’introduction ;
- chapitres et sous-titres hiérarchisés, conclusion et annexes sur des pages dédiées ;
- 43 figures : Gantt, 18 vues de conception et 24 captures réelles ;
- dictionnaire exhaustif des 29 tables, effectifs seedés et extraits nettoyés ;
- légendes solidaires de leurs figures, en-têtes de tableaux répétés et liens internes actifs ;
- aucune clé, aucun jeton et aucune chaîne de connexion dans les annexes ou captures ;
- inspection visuelle de chaque page du PDF, audit d’accessibilité et tests applicatifs avant livraison.
