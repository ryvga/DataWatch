# Démonstration PFE DataWatch — conducteur d’enregistrement

Durée cible : 9 minutes. Résolution : 1920 × 1080. Zoom navigateur : 100 %. Fermer les outils de développement et les notifications système.

## 1. Remettre la démonstration à zéro

```bash
docker compose up -d --wait
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
curl -fsS http://localhost:8000/ready
```

Attendre le message `Acme orders narration is ready for recording`. Garder MailHog ouvert dans un second onglet : `http://localhost:8025`.

## 2. Préparer les deux parcours

- Workspace client : `http://acme-corp.localhost:5173`
- Compte : `mounir@acme.io`
- Mot de passe : `demo1234`
- Portail staff : `http://staff.localhost:5173`

## 3. Conducteur principal

### 00:00–00:45 — Problème et promesse

1. Afficher la page de connexion, puis ouvrir le workspace Acme Corp.
2. Sur **Operations**, montrer le score de santé, les quatre tables suivies et la file d’incidents.
3. Dire une seule idée : DataWatch transforme des mesures techniques en file d’investigation exploitable.

### 00:45–02:45 — De l’alerte au diagnostic

1. Ouvrir **Incidents** puis l’incident P1 `orders — payment_status null rate spiked and freshness breach`.
2. Montrer la sévérité, les signaux mesurés, la chronologie et le contexte de la table.
3. Ouvrir le volet d’analyse IA : causes probables, actions suggérées et requêtes de diagnostic.
4. Faire apparaître la réserve « hypothèses à vérifier ». Ne jamais présenter la narration comme une preuve automatique.
5. Affecter l’incident à **Data Engineering**, puis cliquer **Acknowledge**. Ne pas le résoudre : l’état seedé doit rester réutilisable.

### 02:45–04:20 — Catalogue, profil et moniteurs

1. Ouvrir **Tables**, puis `public.orders`.
2. Parcourir le profil, la fraîcheur, les colonnes, le taux de nullité et l’historique des contrôles.
3. Montrer **Monitor recommendations**, puis le catalogue des moniteurs.
4. Ouvrir le constructeur DSL. Montrer les paramètres et l’aperçu sans enregistrer de règle jetable.

### 04:20–05:40 — Exploitation collective

1. Ouvrir **Reports** et afficher le rapport hebdomadaire.
2. Ouvrir **Teams**, puis **Data Engineering** afin de montrer membres et responsabilités.
3. Dans **Data sources**, montrer la source active et le catalogue des connecteurs.
4. Dans **Settings → Alerts**, montrer la route `pfe-demo@acme.test` et les préférences individuelles.
5. Basculer vers MailHog et afficher le message lié à l’incident.

### 05:40–07:25 — Gouvernance IA observable

1. Ouvrir **AI Governance** et sélectionner le système d’assistance enregistré.
2. Montrer l’usage déclaré, les preuves, les évaluations et la chronologie.
3. Terminer cette séquence sur **Observe only** : DataWatch rend les lacunes visibles ; il ne délivre ni certification juridique ni blocage automatique.

### 07:25–08:35 — Administration multi-tenant

1. Se déconnecter et ouvrir le portail staff.
2. Se connecter avec le compte staff de la seed locale.
3. Montrer le tableau de bord global, la liste des organisations et le détail d’**Acme Corp**.
4. Pointer les utilisateurs et les sources sans emprunter l’identité d’un membre du tenant.

### 08:35–09:00 — Clôture

1. Revenir sur **Operations**.
2. Résumer visuellement le trajet : source → profil → contrôle → incident → investigation → notification.
3. Laisser l’écran sur l’incident P1 et son état reconnu.

## 4. Captures utilisées dans le rapport

Les 24 vues se régénèrent avec :

```bash
cd frontend
npm run capture:pfe
```

La correspondance est directe : `01-workspace-login-report.png` à `24-admin-organization-detail-report.png` deviennent les figures 4.1 à 4.24. Les fichiers sans suffixe `-report` conservent le cadre complet du navigateur ; les variantes `-report` sont recadrées pour la page A4.

## 5. Reprise rapide

- Écran vide ou squelette : attendre le titre réel, puis reprendre la séquence.
- Incident ou narration absent : relancer la seed avec `--reset`.
- Route d’alerte modifiée par un essai : relancer la seed.
- Page staff vide : arrêter l’enregistrement ; la vue doit afficher les utilisateurs et les sources d’Acme Corp.
- Ne montrer aucune variable d’environnement, chaîne de connexion, clé API ou configuration chiffrée.
