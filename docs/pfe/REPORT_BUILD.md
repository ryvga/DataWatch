# Rapport PFE — génération Word

Le document maître est `output/pfe/Rapport_PFE_DataWatch_Mounir_Gaiby.docx`.

## Régénérer le rapport

```bash
/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/pfe/build_rapport_word.py
```

Le générateur lit `docs/pfe/report_source.json` et réutilise les figures sous `docs/diagrams/pfe/` ainsi que les captures sous `docs/screenshots/pfe/`.

## Régénérer les captures de l’application

```bash
docker compose up -d --wait
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
cd frontend
npm run capture:pfe
```

## Contrôles attendus

- format A4 ;
- page de couverture sans numéro ;
- pages préliminaires numérotées en chiffres romains ;
- numérotation arabe à partir de l’introduction ;
- table des matières et liste des figures cliquables et actualisables dans Word ;
- douze figures numérotées et légendées ;
- aucune donnée secrète dans les captures ;
- contrôle visuel du rendu PDF avant livraison.

Le chemin Python ci-dessus correspond au runtime Codex de cette machine. Sur une autre machine, utiliser un environnement Python contenant `python-docx`, `Pillow` et `lxml`.
