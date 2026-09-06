# Extension visuelle et probante du rapport PFE DataWatch

## Décision

Le rapport adopte une composition hybride. Le corps conserve la structure transmise par Dr. Hanine Mohamed, mais chaque mécanisme important reçoit une preuve visuelle lisible. Les vues trop vastes, notamment la base de données de vingt-neuf tables, sont d'abord montrées comme carte générale puis détaillées par domaine. L'annexe conserve le dictionnaire exhaustif et un état chiffré du jeu de démonstration.

## Alternatives examinées

1. **Une planche exhaustive unique.** Elle contient tout, mais devient illisible sur une page A4 et n'aide pas le jury à suivre les responsabilités.
2. **Un catalogue d'annexes.** Il libère le corps du rapport, au prix d'une démonstration technique trop maigre dans les chapitres évalués.
3. **Corps narratif et annexes exhaustives.** Retenue. Les diagrammes par domaine expliquent le système; l'annexe fournit la complétude vérifiable.

## Structure académique préservée

- Pages préliminaires en chiffres romains : dédicace, remerciements, résumé, abstract, table des matières, listes et abréviations.
- Introduction générale limitée et orientée vers le contexte, la problématique, les objectifs et l'organisation.
- Quatre chapitres conformes aux notes de structure : cadre général, état de l'art, analyse et conception, implémentation et tests.
- Chaque chapitre commence par une introduction et se termine par une conclusion.
- Conclusion générale, références puis annexes sur des pages dédiées.
- Titres, sous-titres, figures et tableaux numérotés; renvois explicites dans le texte.

## Corpus visuel cible

### Chapitre 1

- Un vrai diagramme de Gantt horizontal, daté du 1er juin au 31 août 2026.
- Des barres arrondies, des jalons identifiables et une bande distincte indiquant que le produit continue après le PFE.

### Chapitre 3

- Cas d'utilisation global.
- Cas d'utilisation de l'opérateur et de l'administrateur d'organisation.
- Cas d'utilisation du personnel DataWatch.
- Séquence de connexion d'une source et d'activation d'une table.
- Séquence de profilage, détection et création d'incident.
- Séquence d'investigation, d'affectation et d'alerte.
- Séquence de gouvernance IA en mode observe-only.
- Diagramme d'activité du cycle de vie d'un incident.
- Architecture logique en couches.
- Architecture de déploiement Docker.
- Diagrammes de classes séparés : surveillance, collaboration, moniteurs typés, gouvernance IA.
- Schéma relationnel général des vingt-neuf tables, accompagné de vues détaillées par domaine.

### Chapitre 4

Les captures proviennent de la pile Docker seedée, à 1440 x 900, sans squelette de chargement ni secrets visibles. Le corpus couvre : connexion, Opérations, Tables, fiche d'une table, recommandations de moniteurs, constructeur de moniteur, liste des moniteurs, liste des incidents, détail d'incident, narration IA, rapports, équipes, sources, alertes, préférences, systèmes IA, détail de gouvernance, statistiques administrateur et organisations administrées.

Chaque capture dispose d'un court paragraphe qui explique ce que le lecteur doit regarder et pourquoi cet écran prouve une capacité du système. Les images sont suffisamment grandes pour être lues; aucune mosaïque décorative de captures minuscules.

## Base de données et données de démonstration

Le rapport distingue quatre domaines : identité et collaboration, surveillance de données, moniteurs typés, gouvernance IA. Le dictionnaire en annexe liste pour chaque table ses clés, principales colonnes et responsabilité. Un inventaire seedé donne les nombres réellement observés après réinitialisation, sans mot de passe, jeton, clé API ni configuration chiffrée.

## Écriture humaine à variance élevée

La prose garde une cadence irrégulière et une diction précise. Des phrases courtes coupent les développements plus longs. Les verbes décrivent des actions observables; les nombres viennent des preuves du dépôt ou de l'exécution. Le texte évite les transitions automatiques, les trios rhétoriques, les adjectifs gonflés et les affirmations invérifiables. La variété ne doit jamais détériorer la clarté scientifique, falsifier une mesure ou dissimuler une limite.

Un skill global séparé, `human-voice-writing`, rend ces règles disponibles dans tous les projets. Il s'active pour la rédaction ou la révision de textes qui doivent sonner humains et spécifiques, sans imposer le français ni le style PFE aux autres tâches.

## Vérification

- La pile Docker est réinitialisée avant les captures.
- Chaque capture est liée à un écran réellement accessible.
- Les diagrammes sont générés depuis des sources versionnées.
- Les numéros de page sont recalculés après le dernier rendu.
- Le DOCX est rendu page par page; les figures, légendes, tableaux, sommaire, listes et transitions de section sont contrôlés visuellement.
- Le rapport ne transforme ni une capture ni un test local en garantie de production.
