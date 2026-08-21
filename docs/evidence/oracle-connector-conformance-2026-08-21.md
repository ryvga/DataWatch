# Preuve PFE — connecteur Oracle Database (2026-08-21)

## Objet et périmètre

Cette fiche relie les affirmations du rapport PFE au code, aux tests et à leurs limites.
Le connecteur Oracle est **expérimental/core** : il est utilisable pour la connexion, la
découverte, la capture du schéma, le profil planifié et la restitution persistée. Cette
qualification ne signifie pas encore « production stable ».

## Contrat implémenté

- Pilote officiel `python-oracledb` en mode thin asynchrone, sans Oracle Client natif.
- Paramètres structurés `host`, `port`, `service_name`, utilisateur et mot de passe ;
  aucune concaténation de DSN avec des secrets.
- TCPS et vérification d'identité par défaut. Un wallet thin est un répertoire contenant
  `ewallet.pem`; en production, il doit être monté en lecture seule sous
  `ORACLE_WALLET_ROOT`.
- `tcp_connect_timeout` borné entre 1 et 120 secondes ; `call_timeout` borné entre 1 et
  900 secondes et appliqué à chaque aller-retour Oracle.
- Découverte limitée à un propriétaire exact via une variable liée sur `ALL_TABLES`.
  `NUM_ROWS` est une estimation du catalogue et peut être nul ; aucun `COUNT(*)` de
  découverte n'est exécuté.
- Schéma obtenu par variables liées sur `ALL_TAB_COLUMNS`, ordre déterministe
  `COLUMN_ID`, identifiants Oracle échappés par doublement des guillemets.
- Profil « core » en une requête agrégée : ligne, fraîcheur, nullité, cardinalité,
  unicité, bornes numériques/temporelles, moyenne, écart-type et longueurs de texte.
  Il n'existe pas de pré-scan de la table.
- Avant le profil, la session démarre `SET TRANSACTION READ ONLY`; elle termine par un
  rollback. Un échec annule l'appel lorsque le pilote le permet, ferme la connexion et
  empêche sa réutilisation.
- Oracle transforme la chaîne vide en NULL : `empty_rate` est donc volontairement omis.
  Les LOB n'utilisent pas `COUNT(DISTINCT)` ; BLOB/CLOB/NCLOB exposent seulement des
  longueurs agrégées sûres.

## Preuves automatisées locales

Commit fonctionnel : `49175fc`.

Commandes exécutées :

```bash
backend/venv/bin/ruff check backend/app backend/tests
backend/venv/bin/python -m pytest -q backend/tests
cd frontend && npm run build && npm audit --audit-level=high
```

Résultat local : **357 tests réussis, 4 ignorés explicitement** en 19,64 s ; la sélection
Oracle compte **9 réussis, 1 ignoré**. Le frontend a compilé 2 917 modules en 1,61 s et
`npm audit` a signalé 0 vulnérabilité.

Preuve hébergée du commit fonctionnel :
[GitHub Actions 32496502433](https://github.com/ryvga/DataWatch/actions/runs/32496502433).
Les cinq jobs ordinaires sont verts : backend **358 réussis, 3 ignorés en 36,90 s**,
frontend 2 917 modules et 0 vulnérabilité, deux verticales ClickHouse/Trino réussies et
trois parcours navigateur réussis. Le job Oracle est marqué `skipped`, conformément à
son entrée manuelle `run_oracle`; il ne constitue pas une preuve Oracle réelle.

La suite `backend/tests/test_oracle_connector.py` prouve :

1. paramètres thin/TCPS/wallet/timeouts et absence des secrets dans les journaux ;
2. portée propriétaire, estimations catalogue et variables liées ;
3. DDL déterministe avec identifiants adverses ;
4. dialecte Oracle sans syntaxe PostgreSQL, une seule clause `FROM`, fraîcheur native et
   traitement LOB ;
5. transaction read-only, rollback, annulation, fermeture et rejet des écritures ;
6. confinement du wallet en production ;
7. source API → découverte → onboarding avec schéma serveur → worker de profil →
   `TableProfile` persisté → restitution authentifiée.

## Lane Oracle Database Free et limite honnête

Deux points d'entrée reproductibles existent : le profil Compose `test-oracle` et
l'entrée manuelle GitHub Actions `run_oracle=true`. Le 21 août 2026, le premier essai
local de téléchargement de `gvenzl/oracle-free:23-slim-faststart` a été interrompu après
507 secondes : Docker Hub était resté sans progression au-delà de 100 secondes à
805,2 Mo sur 1,202 Go. **Aucune exécution Oracle réelle n'est donc revendiquée par cet
essai.** Les couches partielles du cache local ne constituent pas une preuve de
conformité.

Le rapport PFE doit uniquement revendiquer une preuve réelle lorsque la lane manuelle est
verte et que son URL de run est ajoutée ici et dans Notion. Jusqu'à cette date, la preuve
est composée des contrats pilote simulés, du parseur SQL et du parcours API/worker avec
persistance réelle dans PostgreSQL.

## Sources techniques primaires

- [API `ConnectParams` python-oracledb](https://python-oracledb.readthedocs.io/en/stable/api_manual/connect_params.html)
- [API `AsyncConnection` et `call_timeout`](https://python-oracledb.readthedocs.io/en/stable/api_manual/async_connection.html)
- [Guide asyncio python-oracledb](https://python-oracledb.readthedocs.io/en/v3.4.0/user_guide/asyncio.html)
- [Image Oracle Database Free et variables de test](https://github.com/gvenzl/oci-oracle-free)
- [Action GitHub Oracle Database Free](https://github.com/gvenzl/setup-oracle-free)

## Limites et travaux de promotion

1. Exécuter et archiver la lane Oracle Database Free.
2. Ajouter une lane TCPS réelle avec certificat de confiance et wallet monté en lecture
   seule, puis prouver les erreurs certificat/nom d'hôte.
3. Mesurer p50/p95 et coût de scan sur 10 k, 100 k et 1 M de lignes.
4. Ajouter un exécuteur de moniteurs typés Oracle avec budget de scan conservateur ; le
   connecteur n'annonce actuellement aucun moniteur custom/compilé.
5. Évaluer pool asynchrone, haute disponibilité et authentification Autonomous Database
   avant toute promotion au statut stable.

## Placement dans le rapport PFE

- Chapitre architecture : contrat multi-connecteurs et capacités générées.
- Chapitre sécurité : TLS par défaut, confinement des wallets, secrets non journalisés,
  lecture seule et abandon des sessions douteuses.
- Chapitre validation : tests simulés, vertical API/worker, lane réelle optionnelle et
  distinction explicite entre preuve exécutée et preuve disponible.
- Chapitre limites : coûts non mesurés, TCPS/wallet réel non encore prouvé et absence de
  moniteurs typés Oracle.
