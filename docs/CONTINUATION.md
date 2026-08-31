# DataWatch — Guide de continuité du projet

> Dernière consolidation : 31 août 2026. Ce fichier est le point d'entrée pour
> reprendre DataWatch sur un autre ordinateur ou après une pause.

## 1. Ce qu'est le projet

DataWatch est le projet PFE de **Mounir Gaiby** : une plateforme SaaS
multi-tenant d'observabilité de la qualité des données. L'interface et le
domaine de démonstration utilisent le nom **Panopta** ; le dépôt, le protocole
et le rapport utilisent **DataWatch**. Il s'agit du même produit.

Le flux démontré est : profilage d'une table → détection de signaux → incident
→ narration IA → alerte. La gouvernance IA est un registre de preuves
**observe-only** : elle n'est ni une certification, ni un mécanisme de blocage
d'exécution.

Ne pas promettre une prise en charge universelle des connecteurs : PostgreSQL
est stable, DuckDB et SQLite sont beta ; les autres adaptateurs sont
expérimentaux ou nécessitent une preuve de conformance complémentaire. La
matrice détaillée est dans [README.md](../README.md) et
[docs/connector-catalogue.md](connector-catalogue.md).

## 2. Reprendre sur un nouvel ordinateur

```bash
git clone https://github.com/ryvga/DataWatch.git
cd DataWatch
cp .env.example .env
# Renseigner les secrets locaux dans .env. Ne jamais versionner ce fichier.
docker compose up -d --build --wait
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
curl -fsS http://localhost:8000/ready
```

Le dernier appel doit confirmer que PostgreSQL et Redis sont prêts. Les
identifiants de démonstration sont volontairement locaux et se trouvent dans
[QUICKSTART.md](../QUICKSTART.md). Ils ne doivent jamais être réutilisés en
production.

Les entrées à lire dans cet ordre sont :

1. [CLAUDE.md](../CLAUDE.md) — architecture, règles de sécurité et limites.
2. [QUICKSTART.md](../QUICKSTART.md) — démarrage local fiable.
3. [DEMO.md](../DEMO.md) — enregistrement PFE.
4. [docs/development.md](development.md) — conventions, migrations et tests.
5. [docs/tracking.md](tracking.md) — protocole Linear/Notion.

## 3. Vérifier avant de modifier

Pour la démonstration et la validation applicative :

```bash
docker compose up -d --build --wait
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
cd frontend && npm run build && npm run test:e2e
```

Pour le backend, la vérification stricte requiert les services de test
additionnels décrits dans [docs/development.md](development.md) et dans le
workflow CI. Ne pas confondre des tests `skipped` avec une preuve de livraison.

```bash
docker compose -f docker-compose.test-dbs.yml up -d --wait
cd backend && REQUIRE_TEST_SERVICES=1 venv/bin/python -m pytest -q tests
```

Sur une machine sans environnement Python local compatible, privilégier les
conteneurs Python 3.12 au lieu d'un ancien `venv`. La CI GitHub et les fichiers
dans [docs/evidence/](evidence/) restent les références de preuve historique.

## 4. Démonstration PFE prête à enregistrer

Après le reset de la section 2, suivre exactement [DEMO.md](../DEMO.md) :

1. Acme → **Operations**.
2. Incident P1 `orders` → signaux, narration IA et recommandations.
3. Détail de la table → historique de profils et métrique `payment_status`.
4. Retour incident → accusé de réception et équipe responsable.
5. **Settings → Alerts** puis MailHog → e-mail local P1/P2.
6. **AI Governance** → provenance et frontière observe-only.

Éviter Billing, Reports et l'index Monitors vide durant la démonstration.
Si la narration n'est pas prête, refaire le reset plutôt que d'enregistrer un
état de chargement.

## 5. Livrables PFE versionnés

Les deux livrables produits à partir de l'état du projet sont conservés dans
le dépôt :

- `output/pfe/Rapport_PFE_DataWatch_Mounir_Gaiby.docx`
- `output/pfe/Presentation_PFE_DataWatch_Mounir_Gaiby.pptx`

Le rapport est en français, avec des chiffres romains pour les pages
préliminaires seulement. La présentation contient le parcours de démonstration
ci-dessus. Si le produit évolue, mettre à jour ces livrables et leur source
factuelle dans `docs/evidence/` avant de les régénérer.

## 6. Instantané du suivi externe

Cet instantané a été relevé le **31 août 2026**. Il sert de repère ; avant de
changer un statut, vérifier le code, les tests, la CI et la page externe.

### Linear

- Projet : [DataWatch](https://linear.app/mounir-gaiby/project/datawatch-77f9ab167670), état **In Progress**.
- `MOU-30` — PFE demo polish and recording-ready flow : **Done** (30 août 2026).
- `MOU-24` — AI governance Phase 2 : **In Progress**. L'implémentation et les
  preuves sont documentées, mais le ticket doit être réconcilié avec une
  vérification actuelle avant de le fermer.
- `MOU-25`, `MOU-26` et `MOU-27` : **Backlog**. Ils couvrent respectivement le
  DSL de politiques et les gates, la télémétrie/runtime, puis les packs de
  référentiels et l'évaluation PFE.

### Notion

- [7-Day Build Log](https://app.notion.com/p/374cb96c4e1c813686f6c77c3612bcea) — journal de décisions, problèmes et mesures.
- [Rapport & Presentation Material](https://app.notion.com/p/374cb96c4e1c8126853bc980cbde78e6) — matière source du mémoire.
- [Architecture & Technical Design](https://app.notion.com/p/374cb96c4e1c818b9c54dd576d209d9c) — ADR et conception.
- [Demo Script & Jury Prep](https://app.notion.com/p/374cb96c4e1c81c6911bf6040b81cef1) — parcours jury.

Les entrées Notion historiques peuvent contenir de vieilles commandes locales.
Pour démarrer et enregistrer, `QUICKSTART.md` et `DEMO.md` dans ce dépôt sont
prioritaires, car ils correspondent au chemin Docker vérifié.

## 7. État technique utile et limites à préserver

- État Git lors de cette consolidation : commit de référence `819915b`
  (`feat(pfe): polish recording-ready demo`) sur `main`.
- La chaîne de données est documentée dans [docs/architecture.md](architecture.md).
- Les preuves de gouvernance IA sont dans
  [docs/evidence/ai-governance-phase1-2026-08-21.md](evidence/ai-governance-phase1-2026-08-21.md)
  et [docs/evidence/ai-governance-phase2-2026-08-21.md](evidence/ai-governance-phase2-2026-08-21.md).
- Les mesures de référence et leurs limites sont dans
  [docs/evidence/release-baseline-2026-08-21.md](evidence/release-baseline-2026-08-21.md).
- Les mesures locales historiques et les CI associées ne sont pas des SLA ni
  des résultats de production. Ne pas les présenter comme tels dans le rapport
  ou devant le jury.

## 8. Prochaine séance recommandée

1. Démarrer et exécuter les contrôles de la section 3.
2. Créer ou remettre à jour le ticket Linear correspondant avant de coder.
3. Consigner dans Notion les tests réellement exécutés, les erreurs et les
   mesures obtenues.
4. Réconcilier `MOU-24` avec cette preuve fraîche ; ensuite, choisir `MOU-25`
   seulement si sa portée est nécessaire au PFE.
5. Mettre à jour le rapport et la présentation uniquement avec des résultats
   mesurés et reproductibles.

## 9. Règles de sécurité et de versionnage

- Ne jamais committer `.env`, clés d'API, mots de passe réels, dumps PostgreSQL,
  captures contenant des données client ou dossiers temporaires.
- Créer une migration Alembic pour tout changement de schéma ; ne pas modifier
  une migration existante.
- Toute requête liée à une organisation doit rester filtrée par `org_id`.
- Toute évolution de connecteur doit respecter les limites de capacité et les
  contrôles TLS/lecture seule décrits dans `CLAUDE.md`.
- Une issue Linear n'est terminée que lorsque le code, les tests et la
  documentation Notion concordent.
