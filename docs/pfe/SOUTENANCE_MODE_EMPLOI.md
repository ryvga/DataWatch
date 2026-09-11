# Panopta, soutenance et vidéo

Version du 11 septembre 2026.

## Fichiers à emporter

- `output/pfe/Presentation_Panopta_PFE.pptx`, présentation modifiable en français.
- `output/pfe/Demo_Panopta_Mounir_Gaiby.mp4`, démonstration silencieuse en 1920 × 1080, H.264, 25 images par seconde.
- `docs/pfe/PRESENTATION_NOTES_FR.md`, texte de préparation également présent dans les notes PowerPoint.

Conserver le PowerPoint et le MP4 dans le même dossier. La diapositive 18 contient un lien relatif vers le film. Si PowerPoint demande une autorisation ou ne suit pas ce lien, ouvrir directement le MP4 dans le lecteur vidéo. Le film reste lisible sans lancer l’application et sans connexion réseau.

## Déroulement conseillé

Présenter les diapositives 1 à 17 en environ 12 minutes. Lancer le film de 5 minutes 29 secondes à la diapositive 18. Terminer avec les limites et la conclusion, diapositives 19 et 20, en environ 2 minutes. Les diapositives 21 à 25 servent de réserve pendant les questions.

La période de réalisation du PFE couvre juin à fin août. Le développement continue après cette période. Oyster est l’employeur de Mounir Gaiby, Software Engineer dans Payments. Panopta reste distinct des systèmes internes d’Oyster. Les données du film sont celles du scénario local Acme.

## Repères dans le film

| Temps | Parcours |
| --- | --- |
| 00:09 | Operations et incidents prioritaires |
| 00:24 | Incident orders et analyse IA |
| 00:56 | Recommandations, signaux et attribution |
| 01:29 | Profils et métriques de colonnes |
| 02:10 | Catalogue et constructeur de moniteurs |
| 02:35 | Rapports et équipes |
| 03:08 | Sources et connecteurs |
| 03:31 | Alertes et préférences |
| 03:52 | E-mail reçu dans MailHog |
| 04:04 | Gouvernance IA en mode observation |
| 04:44 | Administration de la plateforme |

## Ce que la capture vérifie

Le parcours ouvre les pages réelles du produit. Il attribue l’incident à Data Engineering et accuse réception. Le message MailHog provient du traitement réel de l’incident. Les captures et réponses API ne sont pas simulées. Le script enregistre 27 étapes. Les diagnostics du parcours enregistrent zéro erreur de page et zéro réponse API v1 en erreur.

L’ouverture du constructeur de moniteurs illustre son interface. Elle ne constitue pas une exécution d’un nouveau moniteur dans ce film. La gouvernance IA reste un prototype de traçabilité en observation. Les métriques et les données historiques du seed ne démontrent pas une charge de production.

Deux imperfections existantes restent visibles dans le produit. La fiche incident affiche parfois « Source name unavailable » malgré son lien fonctionnel vers la table. Le libellé « Healthy » de la fiche table peut sembler incohérent avec un incident ouvert. Ces libellés n’ont pas été modifiés pour fabriquer un état de démonstration. Le score de santé, la confiance et les hypothèses du LLM demandent une explication pendant les questions.

## Reproduire la vidéo

Lire `DEMO.md` et `QUICKSTART.md` pour démarrer et préparer les workspaces de démonstration. Le 11 septembre, le port Redis hôte 6379 était occupé. La pile a démarré avec une surcharge Compose locale utilisant `6381:6379`. Les services internes continuent d’utiliser `redis:6379`.

Après préparation du seed et disponibilité de la narration :

```bash
node scripts/pfe/record_demo.mjs
FFMPEG=/chemin/vers/ffmpeg python3 scripts/pfe/export_demo_video.py
```

Le premier script nécessite les dépendances Playwright du frontend et un navigateur Chromium installé. `FAST=1 node scripts/pfe/record_demo.mjs` capture uniquement les images. Le second nécessite FFmpeg avec libx264 et libass. Il ajoute les repères français et produit un MP4 sans piste audio. Les intermédiaires restent sous `tmp/pfe/demo-video`.

## Reproduire la présentation

Le fichier `scripts/pfe/build_defense.mjs` utilise le runtime JavaScript `@oai/artifact-tool`. Indiquer les chemins locaux via `RUNTIME_NODE_MODULES`, `PRESENTATION_SKILL_DIR` et `RUNTIME_PYTHON` si nécessaire. Le constructeur utilise les images désignées par `docs/pfe/screenshots/demo-2026-09-11/deck-images.json`, conserve les logos originaux et génère les notes françaises.

```bash
node scripts/pfe/build_defense.mjs output/pfe/Presentation_Panopta_PFE_Revision.pptx
```

Le nom de sortie doit être nouveau. Le constructeur vérifie le package et le contenu éditable, puis rend chaque diapositive dans un dossier temporaire pour inspection visuelle.
