# Démonstration PFE DataWatch — parcours à enregistrer

## 1. Préparer l’environnement

```bash
docker compose up -d --wait
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
curl -fsS http://localhost:8000/ready
```

Ne commencer l’enregistrement qu’après le message `Acme orders narration is ready for recording`.

## 2. Ouvrir les écrans

- Application : `http://acme-corp.localhost:5173`
- Compte : `mounir@acme.io`
- Mot de passe : `demo1234`
- Courriels de démonstration : `http://localhost:8025`

## 3. Parcours principal — 6 à 7 minutes

1. Se connecter puis rester sur **Operations**.
2. Montrer les quatre tables surveillées, la source connectée, le score de santé et la file d’incidents.
3. Ouvrir l’incident P1 `orders — payment_status null rate spiked and freshness breach`.
4. Montrer les signaux, la chronologie, l’analyse IA, les causes probables, les actions recommandées et les requêtes de diagnostic.
5. Faire une pause sur les valeurs mesurées, puis sur le libellé qui présente les causes proposées par l’IA comme des hypothèses à vérifier.
6. Ouvrir **View table detail** et montrer le profil, la fraîcheur, le taux de valeurs nulles et l’historique des contrôles.
7. Revenir à l’incident, l’affecter à **Data Engineering**, puis cliquer **Acknowledge**. Ne pas le résoudre.
8. Ouvrir **Settings → Alerts** et montrer la route `pfe-demo@acme.test` à partir de la sévérité P2.
9. Ouvrir MailHog et montrer le message reçu pour l’incident.
10. Ouvrir **AI Governance**, sélectionner le système d’assistance et montrer la carte des usages, la provenance des preuves et les raisons de contrôle.
11. Terminer sur la mention **Observe only** : la fonction rend les lacunes visibles, mais ne certifie pas la conformité et ne bloque pas l’exécution.

## 4. Captures du rapport

Les fichiers sont générés par :

```bash
cd frontend
npm run capture:pfe
```

- `docs/screenshots/pfe/01-operations-report.png` → figure 4.1
- `docs/screenshots/pfe/02-incident-orders-report.png` → figure 4.2
- `docs/screenshots/pfe/03-table-orders-report.png` → figure 4.3
- `docs/screenshots/pfe/04-alerts-report.png` → figure 4.4
- `docs/screenshots/pfe/05-ai-governance-report.png` → figure 4.5

## 5. Plan de secours

- Si l’incident `orders` ou sa narration n’apparaît pas, relancer le seed avec `--reset`.
- Si une route d’alerte manque après les tests navigateur, relancer le seed : le scénario de test nettoie ses données.
- Si une capture affiche un squelette de chargement, ne pas la conserver ; attendre le titre réel de la page et reprendre la capture.
- Ne pas ouvrir Billing, Reports ou un écran vide pendant le parcours principal.
