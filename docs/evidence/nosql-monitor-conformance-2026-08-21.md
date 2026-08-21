# Preuve de conformité PFE — surveillance NoSQL native

Date : 21 août 2026  
Ticket : MOU-17 — MongoDB, Cassandra, Redis

## Question de validation

Le système peut-il surveiller des sources NoSQL avec des plans natifs, bornés et en
lecture seule, sans convertir les définitions en SQL relationnel et sans accepter de
pipeline, CQL ou commande Redis fournis par l'utilisateur ?

## Résultat synthétique

Oui, dans les périmètres expérimentaux documentés ci-dessous. Les trois adaptateurs
compilent la même DSL typée vers un plan immuable propre à la source, persistent le hash
et la version du plan, appliquent une limite dure avant évaluation, puis réutilisent le
même moteur de politique et le même cycle incident ouvert → rétablissement.

| Source | Plan natif | Borne dure | Données lues | Preuve incident |
|---|---|---|---|---|
| MongoDB | `datawatch-v1alpha1-mongodb-1` | `maxDocumentsScanned` | champs typés nécessaires à une agrégation allowlistée | collection vide → incident ; document restauré → résolu |
| Cassandra | `datawatch-v1alpha1-cassandra-1` | `maxRowsScanned` + partition complète | lignes d'une partition liée par requête préparée | partition vide → incident ; ligne restaurée → résolu |
| Redis | `datawatch-v1alpha1-redis-1` | `maxKeysScanned` + pattern fingerprinté | métadonnées TYPE/TTL/mémoire/Hash/Stream ; jamais les valeurs | keyspace vide → incident ; clé restaurée → résolu |

## Chronologie des preuves hébergées

### MongoDB

- `e8bc18b` : profil natif borné par documents, champs et octets ; dérive type/schéma
  échantillonnée ; fraîcheur indexée.
- `7dec519` : plan d'agrégation typé, limites et littéraux protégés, incident/récupération.
- [CI 32487431357](https://github.com/ryvga/DataWatch/actions/runs/32487431357) :
  308 tests backend, 0 ignoré, Ruff/mypy, frontend et 3 scénarios navigateur verts.

### Cassandra

- `4cc5e53` : métadonnées de partition déterministes, bindings obligatoires, requête
  préparée, plafond `LIMIT max + 1`, incident/récupération et service Cassandra 5 requis.
- [CI 32489123968](https://github.com/ryvga/DataWatch/actions/runs/32489123968) :
  315 tests backend, 0 ignoré, 34,88 s.
- Détail : `docs/evidence/cassandra-partition-monitor-conformance-2026-08-21.md`.

### Redis

- `766dd85` : schéma de métadonnées lié au digest du pattern, plan `SCAN` borné,
  allowlist TYPE/PTTL/MEMORY/HLEN/XLEN/XINFO GROUPS, échec fermé sur dépassement,
  parcours incomplet, disparition de clé, changement de scope ou ACL nécessaire.
- [CI 32490547161](https://github.com/ryvga/DataWatch/actions/runs/32490547161) :
  321 tests backend, 0 ignoré, 31,10 s ; Ruff et mypy réussis ; 2 917 modules frontend ;
  0 vulnérabilité ; 3 scénarios navigateur sans erreur console/page/requête.

## Corpus de sécurité

- MongoDB refuse les stages, opérateurs, références et mutations non allowlistés ; les
  chaînes utilisateur sont encapsulées en littéraux.
- Cassandra refuse tout CQL appelant, exige exactement les clés de partition du schéma
  serveur et revalide la requête générée avant `prepare/bind`.
- Redis refuse toute commande appelante ; les tests vérifient l'absence de `GET`, `KEYS`,
  `HGETALL`, `XRANGE`, `EVAL` et assimilés. Un champ nécessaire refusé par ACL ne devient
  jamais un zéro silencieux.

## Limites à ne pas masquer dans le rapport

- MongoDB : schéma issu d'un échantillon ; TLS avec certificat réel, confirmation de
  dérive et charge contrôlée restent à mesurer ; certaines métriques restent bloquées.
- Cassandra : moniteurs manuels uniquement ; pas encore de profil global planifié, TLS
  réel, Cassandra 4, Astra ni charge contrôlée.
- Redis : `SCAN` n'est pas un snapshot transactionnel pendant les mutations concurrentes ;
  TLS réel, Redis 8 et protocole de charge/mutation contrôlée restent à réaliser.

La maturité reste donc « Experimental » pour ces connecteurs. Les preuves démontrent un
vertical sûr et fonctionnel, pas une compatibilité universelle.

## Cartographie vers le rapport PFE

- analyse du besoin : hétérogénéité relationnel/document/wide-column/key-value ;
- conception : DSL commune et planificateurs natifs séparés ;
- sécurité : allowlists, binding, scope fingerprinté et échec fermé ;
- réalisation : adaptateurs, UI source-aware, audit de run et pont incident ;
- tests : corpus de mutation, conteneurs réels et trois scénarios de récupération ;
- discussion : compromis échantillonnage Mongo, partition Cassandra et cohérence `SCAN` ;
- perspectives : TLS réel, versions supplémentaires, charge et précision sous mutation.
