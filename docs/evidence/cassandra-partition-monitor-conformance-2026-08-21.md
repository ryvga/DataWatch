# Preuve de conformité — moniteurs Cassandra bornés par partition

Date de validation : 21 août 2026  
Commit fonctionnel : `4cc5e535b58917c22a23ac1c3536a16557763a4c`  
CI hébergée : [DataWatch CI 32489123968](https://github.com/ryvga/DataWatch/actions/runs/32489123968)

## Objectif PFE

Démontrer qu'un moniteur Cassandra peut mesurer une partition précise sans accepter de
CQL libre, sans lire une table entière et sans produire un résultat à partir d'un
échantillon tronqué. Cette preuve couvre le chemin compilation → exécution → audit →
incident → rétablissement.

## Contrat implémenté

- plan immuable `datawatch-v1alpha1-cassandra-1` lié à l'asset et à l'empreinte du schéma ;
- toutes les clés de partition sont obligatoires dans `partitionBindings`, sans clé
  supplémentaire ;
- identifiants générés exclusivement par le planificateur et valeurs liées par
  `session.prepare(...).bind(...)` ;
- `maxRowsScanned` obligatoire, compris entre 1 et 10 000 ;
- lecture limitée à `maxRowsScanned + 1`, délai pilote borné et taille de fetch bornée ;
- échec fermé `row_scan_budget_exceeded` si la partition dépasse le plafond ;
- métriques et prédicats typés évalués en mémoire uniquement après une lecture complète
  dans le budget ;
- exécution manuelle uniquement dans cette version ; le profilage global Cassandra n'est
  pas revendiqué.

## Preuves exécutables

Le service requis utilise l'image `cassandra:5.0`. Les tests réels créent un keyspace et
une table, vérifient la connexion, la découverte limitée au keyspace configuré, les
marqueurs déterministes de partition/clustering, la préparation et le binding, le plafond
de lignes, puis suppriment les objets et ferment le pilote. Un second test exécute deux
runs persistés : une partition vide ouvre un incident ; l'insertion d'une ligne dans la
même partition fait passer le moniteur et résout l'incident.

La CI Python 3.12 a produit :

- 315 tests backend réussis, 0 ignoré, en 34,88 s ;
- Ruff réussi et mypy réussi sur le noyau des moniteurs sûrs ;
- matrice obligatoire PostgreSQL, Redis, MySQL 8.4, MariaDB 11.4, MongoDB 7,
  SQL Server 2022 et Cassandra 5 ;
- build frontend de 2 917 modules et audit avec 0 vulnérabilité ;
- 3 scénarios navigateur réussis avec `consoleErrors`, `pageErrors` et
  `failedRequests` vides.

La suite locale a produit 314 succès. Son unique échec hors périmètre Cassandra vient du
venv Python 3.14 local : l'extension `pyodbc` ne trouve pas la bibliothèque Homebrew
`libodbc.2.dylib`. La CI de référence installe explicitement UnixODBC et Microsoft ODBC
Driver 18 et a validé ce test SQL Server.

## Limites à conserver dans le rapport

Cette preuve ne valide pas encore le profilage Cassandra planifié à l'échelle d'une
source, un certificat TLS réel, Cassandra 4, Astra DB, ni une charge contrôlée de grande
taille. Elle ne justifie donc pas une maturité supérieure à « Experimental ». Les
moniteurs restent manuels et limités à une partition complètement liée.

## Réutilisation dans le rapport PFE

- chapitre conception : séparation DSL, plan immuable et adaptateur Cassandra ;
- chapitre sécurité : absence de CQL utilisateur, requête préparée et échec fermé ;
- chapitre réalisation : métadonnées de partition, exécution bornée et interface de
  saisie des bindings ;
- chapitre validation : protocole ci-dessus, run CI, résultats chiffrés et scénario
  incident/rétablissement ;
- chapitre limites et perspectives : TLS réel, Cassandra 4/Astra, profilage planifié et
  tests de charge.
