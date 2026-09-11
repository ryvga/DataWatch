# Panopta, notes de soutenance

Présentation principale : diapositives 1 à 20. Réserves : 21 à 25.

## 1. Panopta

Bonjour. Je suis Mounir Gaiby, étudiant en 3CI Big Data et Intelligence Artificielle à l’ISGA Casablanca et Software Engineer dans l’équipe Payments d’Oyster. Je présente Panopta, une plateforme de surveillance de la qualité des données enrichie par l’IA. Le nom évoque Argos Panoptès, le gardien aux multiples yeux de la mythologie grecque. Je remercie Allah, puis mon encadrant, Pr. HANINE MOHAMED, pour son accompagnement. Sources : rapport PFE, témoignage du porteur du projet, logos institutionnels conservés dans docs/pfe/assets. Logo Oyster : https://www.oysterhr.com/media-kit

## 2. Le fil de la soutenance

Durée cible : environ quinze minutes de présentation, puis la vidéo. Le plan suit la logique du rapport : contexte général, analyse et conception, réalisation, validation et perspectives. Les diapositives de réserve servent aux questions du jury.

## 3. Oyster et mon rôle dans Payments

J’occupe un emploi de Software Engineer au sein de l’équipe Payments d’Oyster. Mon activité porte sur les tâches liées aux paiements. Le sujet du PFE s’appuie sur les préoccupations de fiabilité que ce travail m’amène à rencontrer. Panopta reste ici un prototype académique présenté avec des données de démonstration. Je ne revendique ni un déploiement en production chez Oyster, ni l’utilisation de ses données internes. Sources : informations de Mounir Gaiby et scripts/pfe/build_rapport_word.py, section 1.1. Oyster : https://www.oysterhr.com/media-kit

## 4. Une donnée incorrecte peut rester silencieuse

Prenons le scénario de démonstration : une proportion inhabituelle de statuts de paiement devient nulle. La base répond toujours. Une vérification de disponibilité ne suffit donc pas à décrire la qualité de son contenu. Je cherche à détecter le signal, à conserver les observations qui l’expliquent et à donner à l’opérateur une piste d’investigation. La panne et ses chiffres appartiennent au jeu de données local, pas aux systèmes d’Oyster. Source : scripts/quickstart.py et backend/app/services/anomaly.py.

## 5. Le besoin fonctionnel

Les besoins s’organisent autour du travail d’investigation. Un administrateur relie les sources et paramètre la surveillance. L’opérateur traite les incidents. Le responsable examine l’historique et les rapports. La séparation des organisations conditionne tous ces parcours. Les diagrammes de classes et de séquence en réserve détaillent ce périmètre. Source : frontend/src/App.jsx, backend/app/routers, docs/architecture.md.

## 6. Trois mois de réalisation, puis la consolidation

Cette vue synthétise la période de réalisation retenue pour le PFE, de juin à fin août 2026. Les activités se chevauchent car les tests et les retours du produit accompagnent le développement. Le projet continue après cette période. Les barres représentent une synthèse des lots de travail, et non un relevé quotidien des heures. Sources : historique Git, docs/tracking.md et rapport PFE.

## 7. Une vue de travail centrée sur les incidents

L’écran Operations rassemble les incidents à traiter et les tables suivies. Je montre la capture comme point d’entrée du parcours réel. Le score de santé est un indicateur interne qui agrège les signaux récents. Il ne faut pas le lire comme une garantie contractuelle. Le nombre d’incidents et les métriques visibles correspondent au jeu de données de démonstration. Sources : frontend/src/pages/Overview.jsx et capture locale.

## 8. Architecture de Panopta

Le navigateur utilise une API FastAPI. Les tâches de profilage passent par Celery et Redis pour s’exécuter hors de la requête utilisateur. Le connecteur travaille sur la source, puis l’application conserve profils, contrôles et incidents dans PostgreSQL. Le fournisseur de langage intervient pour l’explication de l’incident. Cette séparation permet de faire évoluer les workers sans réécrire l’interface. Sources : docker-compose.yml, backend/app/tasks.py et backend/app/services/profiler.py.

## 9. Le lien avec Big Data

Le lien avec Big Data tient à la façon de traiter des données hétérogènes sans rapatrier les tables métier. Le profilage calcule des agrégats dans la source, avec des limites propres à chaque connecteur. Les tâches asynchrones séparent collecte et navigation. Les profils forment un historique exploitable par les détecteurs. Le prototype ne dispose pas encore d’un benchmark distribué de grande volumétrie. Kafka n’appartient pas à cette version du code. Sources : backend/app/services/profiler.py, backend/app/connectors et docker-compose.yml.

## 10. Les profils donnent une mémoire à la table

Un profil conserve notamment le volume, la fraîcheur, l’empreinte du schéma et les métriques par colonne. Ces observations permettent de comparer une table à son propre historique. La capture montre le profil d’orders dans le scénario local. L’application effectue surtout des agrégations, avec des requêtes complémentaires pour certaines distributions. Elle ne réduit donc pas tous les cas à une seule requête universelle. Source : backend/app/services/profiler.py et capture locale.

## 11. La détection combine plusieurs méthodes

Les règles couvrent les situations directement interprétables, comme une table vide ou une fraîcheur dépassée. Les statistiques comparent le profil à l’historique. Isolation Forest ajoute une détection multivariée lorsque les observations sont suffisantes. STL travaille sur une période de sept observations dans le code actuel. La sévérité provient du moteur de contrôle et des règles métier. Une campagne annotée doit encore mesurer précision, rappel et faux positifs. Source : backend/app/services/anomaly.py.

## 12. Le LLM explique les signaux observés

Le service de narration reçoit un contexte construit à partir de l’incident et de ses métriques. Le modèle produit un résumé, des causes possibles et des actions de diagnostic. L’application valide une sortie structurée. La cause proposée reste une hypothèse que l’opérateur doit vérifier. Le délai dépend aussi du fournisseur externe. Source : backend/app/services/llm.py, tests/test_llm.py et capture locale.

## 13. Un incident conserve le fil de l’enquête

L’incident relie la détection à un travail d’équipe. Sa page rassemble les contrôles déclenchés, l’historique et l’explication disponible. L’opérateur peut accuser réception et attribuer un responsable. La déduplication évite de créer une nouvelle fiche à chaque profil en échec sur la même table. La résolution doit correspondre à une décision ou à une récupération selon le parcours concerné. Sources : backend/app/services/incident.py et frontend/src/pages/IncidentDetail.jsx.

## 14. Les alertes prolongent le parcours

Panopta dispose de routes d’alerte. Pour la démonstration, les e-mails passent par MailHog, un récepteur local qui permet de vérifier leur contenu sans envoyer de message à une personne réelle. Je montre le lien entre l’incident et l’alerte. Cette vérification locale ne mesure pas la délivrabilité d’un service de messagerie en production. Sources : backend/app/services/alert.py, scripts/quickstart.py et capture MailHog.

## 15. Gouvernance IA, un prototype en observation

Ce module constitue un petit prototype de gouvernance IA. Il inventorie les systèmes, leurs versions, les usages déclarés et les éléments de preuve. Il rend visibles des contrôles manquants, périmés ou en échec. La confiance affichée décrit la couverture des preuves selon la formule interne. Elle ne représente pas la probabilité qu’un modèle soit sûr. Le module doit encore évoluer et ne certifie ni conformité, ni équité, ni usage réel des données à l’exécution. Sources : docs/ai-governance.md et backend/app/services/ai_governance.py.

## 16. La séparation des organisations

Chaque client utilise un espace de travail identifié par son sous-domaine. Le jeton d’accès transporte le contexte de l’organisation et les routes filtrent les données concernées. Les secrets de connexion utilisent un chiffrement avec une clé dérivée par organisation. L’administration de la plateforme dispose d’un portail séparé. Cette architecture doit être vérifiée par des tests d’accès croisés. Sources : backend/app/auth.py, backend/app/services/crypto.py et backend/app/routers/auth.py.

## 17. La validation suit les parcours du produit

La validation combine les tests unitaires des détecteurs et de la narration avec des parcours de navigateur exécutés sur une pile locale. Les captures et la vidéo de cette livraison montrent ce qui a été parcouru. Les mesures historiques disposent de leur date et de leur méthode. Un test ignoré ne démontre pas qu’une fonctionnalité fonctionne. Je conserve aussi les limites : connecteurs expérimentaux, charge soutenue et précision des détecteurs. Sources : backend/tests, frontend/playwright, docs/evidence.

## 18. Démonstration de Panopta

Lancer le fichier Demo_Panopta_Mounir_Gaiby.mp4 placé dans le même dossier que la présentation. La vidéo ne contient pas de narration et utilise des repères français. Elle enregistre l’application locale avec ses données de démonstration. En cas de lien bloqué par PowerPoint, ouvrir directement le MP4 depuis le dossier. Présenter brièvement l’incident avant de lancer la vidéo, puis reprendre sur les limites. Source : vidéo locale et scripts/pfe/record_demo.mjs.

## 19. Les limites orientent la suite du travail

Le prototype a une chaîne fonctionnelle, mais plusieurs qualités doivent encore être mesurées. Je veux tester la précision des détecteurs sur des scénarios annotés, mesurer la charge avec plusieurs workers, puis consolider la fiabilité des connecteurs selon leur niveau de support. La gouvernance IA reste une extension exploratoire à étendre. L’objectif de la semaine de soutenance est la stabilité de la démonstration. La suite du produit dépasse le calendrier du PFE. Sources : README.md, docs/connector-catalogue.md et docs/ai-governance.md.

## 20. Panopta, un socle pour poursuivre

Ce projet relie l’ingénierie des données, la détection statistique et l’assistance par un modèle de langage. Le résultat principal est une chaîne d’investigation visible dans l’application : les observations conduisent à un incident, l’incident porte une explication et l’équipe dispose d’un suivi. Mon travail chez Oyster a donné un contexte concret à ce besoin de fiabilité. Je vous remercie pour votre attention et je suis prêt à répondre à vos questions.

## 21. Modèle de données, le cœur du suivi

Ce diagramme simplifié présente le cœur du modèle métier. Une organisation possède des sources. Chaque source expose des tables suivies. Une table possède un historique de profils, des résultats de contrôle et des incidents. Les autres familles couvrent utilisateurs, moniteurs, alertes et gouvernance IA. Le schéma complet est dans le rapport et les migrations Alembic. Source : backend/app/models et docs/pfe/database_evidence.json.

## 22. Séquence de profilage et d’alerte

Le planificateur envoie une tâche au worker. Le worker appelle le connecteur et conserve le profil. Les contrôles évaluent les signaux et créent ou enrichissent l’incident. La narration et les alertes prolongent ce traitement. Cette vue condense la séquence, avec persistance dans PostgreSQL. Les tâches et branches détaillées figurent dans backend/app/tasks.py. Elle évite de confondre la durée de l’API et celle du fournisseur de langage.

## 23. Mesures locales de référence

Mesures historiques du 21 août 2026. Trente requêtes séquentielles locales par endpoint après préparation de la pile. Le graphique conserve les p95 en millisecondes : sources 2,59, tables 4,30, incidents 3,91 et santé organisationnelle 144,27. La santé agrège davantage de dimensions. Ces valeurs permettent une comparaison de régression dans un environnement comparable. Elles ne mesurent ni la concurrence, ni la charge soutenue, ni un engagement de service. Source : docs/evidence, release hardening du 21 août, et Notion 7-Day Build Log.

## 24. Les fonctions complémentaires

Les fonctions de collaboration et de reporting donnent au prototype une portée SaaS. Cette capture montre les rapports accessibles dans le produit. Le catalogue de moniteurs, les équipes, les sources et l’administration complètent le parcours. La vidéo fournit une visite plus large de ces fonctions. Si le jury demande un détail, revenir à l’application et distinguer ce qui a été exécuté de ce qui reste expérimental. Sources : frontend/src/pages et captures locales.

## 25. Questions techniques à préparer

Pourquoi ce sujet en Big Data et IA ? Il combine traitement de données hétérogènes, profils agrégés et détection statistique ou multivariée, puis narration LLM. Pourquoi pas Kafka ? Le traitement actuel est périodique et repose sur Celery et Redis. Un flux événementiel deviendrait pertinent avec un besoin documenté. Le LLM prouve-t-il la cause ? Non, il produit des hypothèses à vérifier. La gouvernance est-elle complète ? Non, c’est un prototype d’inventaire, de preuves et de contrôles en observation.
