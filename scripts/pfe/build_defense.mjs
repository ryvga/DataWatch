/** Rebuild the French Panopta defense deck. Requires the Codex artifact runtime. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const runtime = process.env.RUNTIME_NODE_MODULES || '/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const require = createRequire(path.join(runtime, '_resolve.cjs'));
const { Presentation, PresentationFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const sharp = require('sharp');
const skill = process.env.PRESENTATION_SKILL_DIR || '/Users/mounir/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations';
const { finalizePresentation, applyPresentationChartFont } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href);
const tmp = path.join(root, 'tmp/pfe/defense-2026-09-11');
const finalPath = path.resolve(process.argv[2] || path.join(root, 'output/pfe/Presentation_Panopta_PFE.pptx'));
await fs.mkdir(tmp, { recursive: true });
await fs.mkdir(path.dirname(finalPath), { recursive: true });
const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const C = { paper:'#F7F5F0', ink:'#212322', mute:'#626660', red:'#B5233C', line:'#D7D8D1', white:'#FFFFFF', dark:'#192421', green:'#326B59' };
const FONT = 'Arial';
const notes = [];
let shots = {};
try { shots = JSON.parse(await fs.readFile(path.join(root, 'docs/pfe/screenshots/demo-2026-09-11/deck-images.json'), 'utf8')); } catch {}
const fallback = {
 operations:'docs/screenshots/pfe/02-operations-report.png', incident:'docs/screenshots/pfe/05-incident-orders-report.png',
 table:'docs/screenshots/pfe/07-table-orders-report.png', narration:'docs/screenshots/pfe/06-incident-narration-report.png',
 governance:'docs/screenshots/pfe/19-ai-governance-detail-report.png', sources:'docs/screenshots/pfe/14-data-sources.png',
 monitors:'docs/screenshots/pfe/10-monitor-builder.png', reports:'docs/screenshots/pfe/11-weekly-reports.png',
 teams:'docs/screenshots/pfe/12-teams.png', alerts:'docs/screenshots/pfe/16-alert-routes.png',
 mail:'docs/screenshots/pfe/13-mailhog.png', staff:'docs/screenshots/pfe/23-admin-dashboard.png',
};
function text(s, value, x,y,w,h,size=26,color=C.ink,bold=false,align='left') {
 const sh=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text=value; sh.text.style={typeface:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};return sh;
}
function line(s,x,y,w,color=C.line) {s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},fill:'none',line:{fill:color,width:1}});}
function box(s,label,x,y,w,h,{fill=C.white,color=C.ink,size=24}={}) {
 const sh=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:C.line,width:1}});
 sh.text=label;sh.text.style={typeface:FONT,fontSize:size,color,alignment:'center',verticalAlignment:'middle',insets:{left:12,right:12,top:12,bottom:12}};return sh;
}
function connect(s,a,b,from='right',to='left',color=C.red) {s.shapes.connect(a,b,{kind:'elbow',fromSide:from,toSide:to,line:{fill:color,width:2},tail:{type:'triangle',width:'sm',length:'sm'}});}
function slide(title, section, note, {dark=false}={}) {
 const s=p.slides.add();s.background.fill=dark?C.dark:C.paper;
 const fg=dark?C.white:C.ink;
 text(s,section.toUpperCase(),56,34,1120,25,14,dark?'#A9C1B7':C.red,true);
 text(s,title,56,82,1168,106,44,fg,true);
 text(s,String(p.slides.items.length).padStart(2,'0'),1178,678,44,20,13,dark?'#A9C1B7':C.mute,false,'right');
 s.speakerNotes.textFrame.setText(note);notes.push({slide:p.slides.items.length,title,notes:note});return s;
}
async function img(s,rel,x,y,w,h,alt,fit='contain') {
 const file=path.isAbsolute(rel)?rel:path.join(root,rel);
 s.images.add({blob:new Uint8Array(await fs.readFile(file)),contentType:file.endsWith('.jpg')?'image/jpeg':'image/png',alt,fit,position:{left:x,top:y,width:w,height:h}});
}
async function screenshot(s,key,x=56,y=202,w=862,h=430) {
 const file=shots[key] || fallback[key];if(!file)throw new Error('Missing screenshot key '+key);
 const crops={operations:{left:.23,right:.10,top:0,bottom:.35},narration:{left:.235,right:.305,top:.36,bottom:.21},incident:{left:.23,right:.10,top:.06,bottom:.32},table:{left:.13,right:.10,top:.05,bottom:.22},governance:{left:.12,right:.008,top:.015,bottom:.36},alerts:{left:.23,right:.10,top:0,bottom:.30},reports:{left:.13,right:.10,top:.03,bottom:.25}};
 const original=await fs.readFile(path.resolve(root,file));const metadata=await sharp(original).metadata();const crop=crops[key];
 const bytes=crop?await sharp(original).extract({left:Math.round(metadata.width*crop.left),top:Math.round(metadata.height*crop.top),width:Math.floor(metadata.width*(1-crop.left-crop.right)),height:Math.floor(metadata.height*(1-crop.top-crop.bottom))}).png().toBuffer():original;
 s.images.add({blob:new Uint8Array(bytes),contentType:'image/png',alt:'Détail de la capture réelle Panopta, '+key,fit:'contain',position:{left:x,top:y,width:w,height:h}});
}
function aside(s,label,body,{y=218,dark=false}={}) {text(s,label,952,y,272,62,28,dark?'#E7B8BD':C.red,true);text(s,body,952,y+82,266,280,23,dark?C.white:C.ink);}
function row(s,num,title,body,y) {text(s,num,58,y,80,66,50,C.red,true);text(s,title,165,y+2,990,45,30,C.ink,true);text(s,body,165,y+52,1000,70,24,C.mute);}

// 01. Institutional cover, with original school and employer marks.
{
 const s=p.slides.add();s.background.fill=C.paper;
 await img(s,'docs/pfe/assets/isga-logo.png',56,32,177,94,'Logo ISGA Casablanca');
 await img(s,'docs/pfe/assets/oyster-logo-black.png',1010,44,212,70,'Logo Oyster');
 line(s,56,149,1168,C.red);line(s,56,156,1168,C.red);
 text(s,'PROJET DE FIN D’ÉTUDES',56,196,1100,30,18,C.red,true);
 text(s,'Panopta',50,244,1170,120,104,C.ink,true);
 text(s,'Surveillance de la qualité des données\net explication des incidents par l’IA',56,381,1150,95,38,C.ink);
 text(s,'Pour l’obtention du diplôme d’Ingénieur d’État\nBig Data et Intelligence Artificielle',56,508,1050,64,23,C.mute);
 text(s,'Réalisé par\nMounir Gaiby',56,619,340,57,20,C.ink);
 text(s,'Encadré par\nPr. HANINE MOHAMED',474,619,470,57,20,C.ink);
 text(s,'ISGA Casablanca\n2025-2026',1000,619,225,57,20,C.ink,false,'right');
 const n='Bonjour. Je suis Mounir Gaiby, étudiant en 3CI Big Data et Intelligence Artificielle à l’ISGA Casablanca et Software Engineer dans l’équipe Payments d’Oyster. Je présente Panopta, une plateforme de surveillance de la qualité des données enrichie par l’IA. Le nom évoque Argos Panoptès, le gardien aux multiples yeux de la mythologie grecque. Je remercie Allah, puis mon encadrant, Pr. HANINE MOHAMED, pour son accompagnement. Sources : rapport PFE, témoignage du porteur du projet, logos institutionnels conservés dans docs/pfe/assets. Logo Oyster : https://www.oysterhr.com/media-kit';
 s.speakerNotes.textFrame.setText(n);notes.push({slide:1,title:'Panopta',notes:n});
}
{
 const s=slide('Le fil de la soutenance','Parcours','Durée cible : environ quinze minutes de présentation, puis la vidéo. Le plan suit la logique du rapport : contexte général, analyse et conception, réalisation, validation et perspectives. Les diapositives de réserve servent aux questions du jury.');
 row(s,'01','Le besoin métier','Un contexte de paiements et une question de fiabilité des données.',216);
 row(s,'02','La conception et la réalisation','Une architecture SaaS, des profils statistiques et une assistance IA.',360);
 row(s,'03','Les résultats et la démonstration','Un incident concret, les limites du prototype et la suite du projet.',504);
}
{
 const s=slide('Oyster et mon rôle dans Payments','Contexte professionnel','J’occupe un emploi de Software Engineer au sein de l’équipe Payments d’Oyster. Mon activité porte sur les tâches liées aux paiements. Le sujet du PFE s’appuie sur les préoccupations de fiabilité que ce travail m’amène à rencontrer. Panopta reste ici un prototype académique présenté avec des données de démonstration. Je ne revendique ni un déploiement en production chez Oyster, ni l’utilisation de ses données internes. Sources : informations de Mounir Gaiby et scripts/pfe/build_rapport_word.py, section 1.1. Oyster : https://www.oysterhr.com/media-kit');
 await img(s,'docs/pfe/assets/oyster-logo-black.png',64,227,460,150,'Logo officiel Oyster');
 text(s,'Software Engineer\nÉquipe Payments',655,219,540,115,40,C.ink,true);
 text(s,'Un emploi dans une équipe produit.\nDes responsabilités liées aux paiements.',655,369,540,100,27,C.mute);
 line(s,56,520,1168);text(s,'La fiabilité d’un paiement dépend aussi de la qualité des données qui le décrivent.',56,562,1100,90,32,C.ink);
}
{
 const s=slide('Une donnée incorrecte peut rester silencieuse','Problématique','Prenons le scénario de démonstration : une proportion inhabituelle de statuts de paiement devient nulle. La base répond toujours. Une vérification de disponibilité ne suffit donc pas à décrire la qualité de son contenu. Je cherche à détecter le signal, à conserver les observations qui l’expliquent et à donner à l’opérateur une piste d’investigation. La panne et ses chiffres appartiennent au jeu de données local, pas aux systèmes d’Oyster. Source : scripts/quickstart.py et backend/app/services/anomaly.py.');
 text(s,'payment_status',56,219,1110,66,52,C.red,true);
 text(s,'La table répond.\nCertains statuts deviennent nuls.',56,310,1050,128,45,C.ink,true);
 text(s,'Comment détecter une dégradation, expliquer les signaux\net orienter l’équipe avant qu’elle ne perde du temps ?',56,510,1120,110,30,C.mute);
}
{
 const s=slide('Le besoin fonctionnel','Analyse des besoins','Les besoins s’organisent autour du travail d’investigation. Un administrateur relie les sources et paramètre la surveillance. L’opérateur traite les incidents. Le responsable examine l’historique et les rapports. La séparation des organisations conditionne tous ces parcours. Les diagrammes de classes et de séquence en réserve détaillent ce périmètre. Source : frontend/src/App.jsx, backend/app/routers, docs/architecture.md.');
 row(s,'01','Surveiller','Sources, tables, profils et règles de contrôle configurables.',207);
 row(s,'02','Investiguer','Incidents priorisés, observations persistées et hypothèses de l’IA.',351);
 row(s,'03','Organiser le suivi','Équipes, notifications, rapports et séparation des organisations.',495);
}
{
 const s=slide('Trois mois de réalisation, puis la consolidation','Organisation du projet','Cette vue synthétise la période de réalisation retenue pour le PFE, de juin à fin août 2026. Les activités se chevauchent car les tests et les retours du produit accompagnent le développement. Le projet continue après cette période. Les barres représentent une synthèse des lots de travail, et non un relevé quotidien des heures. Sources : historique Git, docs/tracking.md et rapport PFE.');
 const x=420, step=242;['JUIN','JUILLET','AOÛT'].forEach((m,i)=>text(s,m,x+i*step,214,220,28,21,C.red,true));
 const tasks=[['Cadrage et socle SaaS',0,1.0],['Connecteurs et détection',0.45,1.4],['Moniteurs et gouvernance IA',1.2,1.6],['Validation et rapport',1.7,1.3]];
 tasks.forEach(([label,start,duration],i)=>{const y=278+i*76;text(s,label,56,y+7,345,50,24,C.ink);line(s,x,y+43,726);s.shapes.add({geometry:'rect',position:{left:x+start*step,top:y,width:duration*step-10,height:32},fill:i===3?C.red:C.green,line:{fill:'none',width:0}});});
 text(s,'SEPTEMBRE ET APRÈS',56,612,450,28,18,C.red,true);text(s,'Démonstration, mesure à plus grande échelle et poursuite du produit.',420,605,770,60,23,C.ink);
}
{
 const s=slide('Une vue de travail centrée sur les incidents','Réalisation','L’écran Operations rassemble les incidents à traiter et les tables suivies. Je montre la capture comme point d’entrée du parcours réel. Le score de santé est un indicateur interne qui agrège les signaux récents. Il ne faut pas le lire comme une garantie contractuelle. Le nombre d’incidents et les métriques visibles correspondent au jeu de données de démonstration. Sources : frontend/src/pages/Overview.jsx et capture locale.');
 await screenshot(s,'operations');aside(s,'Le point d’entrée','La priorité apparaît avant le détail technique.\n\nL’opérateur peut ouvrir l’incident ou revenir à la table.');
}
{
 const s=slide('Architecture de Panopta','Conception','Le navigateur utilise une API FastAPI. Les tâches de profilage passent par Celery et Redis pour s’exécuter hors de la requête utilisateur. Le connecteur travaille sur la source, puis l’application conserve profils, contrôles et incidents dans PostgreSQL. Le fournisseur de langage intervient pour l’explication de l’incident. Cette séparation permet de faire évoluer les workers sans réécrire l’interface. Sources : docker-compose.yml, backend/app/tasks.py et backend/app/services/profiler.py.');
 const ui=box(s,'Interface React',56,239,253,84), api=box(s,'API FastAPI',384,239,253,84), db=box(s,'PostgreSQL\nProfils et incidents',929,239,294,84);
 connect(s,ui,api);connect(s,api,db);
 const jobs=box(s,'Celery + Redis\nTraitements asynchrones',384,429,302,100), source=box(s,'Sources de données\nConnecteurs',56,429,253,100), llm=box(s,'Fournisseur LLM\nExplication structurée',929,429,294,100);
 connect(s,api,jobs,'bottom','top');connect(s,jobs,source,'left','right');connect(s,jobs,llm);connect(s,jobs,db,'right','bottom');
 text(s,'Le planificateur déclenche les profils selon la cadence de chaque table.',56,612,1100,40,25,C.mute);
}
{
 const s=slide('Le lien avec Big Data','Ingénierie des données','Le lien avec Big Data tient à la façon de traiter des données hétérogènes sans rapatrier les tables métier. Le profilage calcule des agrégats dans la source, avec des limites propres à chaque connecteur. Les tâches asynchrones séparent collecte et navigation. Les profils forment un historique exploitable par les détecteurs. Le prototype ne dispose pas encore d’un benchmark distribué de grande volumétrie. Kafka n’appartient pas à cette version du code. Sources : backend/app/services/profiler.py, backend/app/connectors et docker-compose.yml.');
 row(s,'01','Calcul au plus près de la source','Profils agrégés, sans réplication complète des tables métier.',207);
 row(s,'02','Hétérogénéité des données','Connecteurs et capacités explicites selon le moteur.',351);
 row(s,'03','Exécution asynchrone','Workers, historique des profils et surveillance périodique.',495);
}
{
 const s=slide('Les profils donnent une mémoire à la table','Profilage','Un profil conserve notamment le volume, la fraîcheur, l’empreinte du schéma et les métriques par colonne. Ces observations permettent de comparer une table à son propre historique. La capture montre le profil d’orders dans le scénario local. L’application effectue surtout des agrégations, avec des requêtes complémentaires pour certaines distributions. Elle ne réduit donc pas tous les cas à une seule requête universelle. Source : backend/app/services/profiler.py et capture locale.');
 await screenshot(s,'table');aside(s,'Ce que l’on mesure','Volume et fraîcheur.\n\nValeurs nulles, cardinalité et distributions.\n\nÉvolution dans le temps.');
}
{
 const s=slide('La détection combine plusieurs méthodes','Intelligence artificielle','Les règles couvrent les situations directement interprétables, comme une table vide ou une fraîcheur dépassée. Les statistiques comparent le profil à l’historique. Isolation Forest ajoute une détection multivariée lorsque les observations sont suffisantes. STL travaille sur une période de sept observations dans le code actuel. La sévérité provient du moteur de contrôle et des règles métier. Une campagne annotée doit encore mesurer précision, rappel et faux positifs. Source : backend/app/services/anomaly.py.');
 const cols=[56,472,886];const content=[['Règles métier','Table vide\nFraîcheur dépassée\nSchéma modifié','Utilisables dès le premier profil'],['Statistiques','Z-score\nCardinalité\nCroissance du volume','Comparaison à l’historique'],['Apprentissage','Isolation Forest\nDécomposition STL','Historique suffisant requis']];
 content.forEach(([h,b,f],i)=>{text(s,h,cols[i],219,352,65,32,C.red,true);text(s,b,cols[i],316,352,170,29,C.ink);line(s,cols[i],523,330);text(s,f,cols[i],551,350,90,23,C.mute);});
}
{
 const s=slide('Le LLM explique les signaux observés','Assistance à l’investigation','Le service de narration reçoit un contexte construit à partir de l’incident et de ses métriques. Le modèle produit un résumé, des causes possibles et des actions de diagnostic. L’application valide une sortie structurée. La cause proposée reste une hypothèse que l’opérateur doit vérifier. Le délai dépend aussi du fournisseur externe. Source : backend/app/services/llm.py, tests/test_llm.py et capture locale.');
 await screenshot(s,'narration');aside(s,'Une aide au diagnostic','Contexte mesuré.\n\nHypothèses explicites.\n\nActions à vérifier par l’opérateur.');
}
{
 const s=slide('Un incident conserve le fil de l’enquête','Traitement des incidents','L’incident relie la détection à un travail d’équipe. Sa page rassemble les contrôles déclenchés, l’historique et l’explication disponible. L’opérateur peut accuser réception et attribuer un responsable. La déduplication évite de créer une nouvelle fiche à chaque profil en échec sur la même table. La résolution doit correspondre à une décision ou à une récupération selon le parcours concerné. Sources : backend/app/services/incident.py et frontend/src/pages/IncidentDetail.jsx.');
 await screenshot(s,'incident');aside(s,'Le suivi humain','Priorité et statut.\n\nAccusé de réception.\n\nAttribution à une équipe.');
}
{
 const s=slide('Les alertes prolongent le parcours','Notifications','Panopta dispose de routes d’alerte. Pour la démonstration, les e-mails passent par MailHog, un récepteur local qui permet de vérifier leur contenu sans envoyer de message à une personne réelle. Je montre le lien entre l’incident et l’alerte. Cette vérification locale ne mesure pas la délivrabilité d’un service de messagerie en production. Sources : backend/app/services/alert.py, scripts/quickstart.py et capture MailHog.');
 await screenshot(s,'alerts');aside(s,'Un routage explicite','Canal et seuil de sévérité.\n\nRéception locale de l’e-mail dans MailHog pendant la démo.');
}
{
 const s=slide('Gouvernance IA, un prototype en observation','Extension exploratoire','Ce module constitue un petit prototype de gouvernance IA. Il inventorie les systèmes, leurs versions, les usages déclarés et les éléments de preuve. Il rend visibles des contrôles manquants, périmés ou en échec. La confiance affichée décrit la couverture des preuves selon la formule interne. Elle ne représente pas la probabilité qu’un modèle soit sûr. Le module doit encore évoluer et ne certifie ni conformité, ni équité, ni usage réel des données à l’exécution. Sources : docs/ai-governance.md et backend/app/services/ai_governance.py.');
 await screenshot(s,'governance');aside(s,'Périmètre actuel','Inventaire et traçabilité.\n\nContrôles expliqués.\n\nObservation et alerte.\n\nTravail encore exploratoire.');
}
{
 const s=slide('La séparation des organisations','Architecture SaaS','Chaque client utilise un espace de travail identifié par son sous-domaine. Le jeton d’accès transporte le contexte de l’organisation et les routes filtrent les données concernées. Les secrets de connexion utilisent un chiffrement avec une clé dérivée par organisation. L’administration de la plateforme dispose d’un portail séparé. Cette architecture doit être vérifiée par des tests d’accès croisés. Sources : backend/app/auth.py, backend/app/services/crypto.py et backend/app/routers/auth.py.');
 const a=box(s,'Organisation A\nEspace de travail A',56,242,340,106),b=box(s,'Organisation B\nEspace de travail B',56,430,340,106),api=box(s,'API\nContexte organisation',518,323,287,130),db=box(s,'PostgreSQL\nDonnées filtrées par org_id',928,323,296,130);
 connect(s,a,api);connect(s,b,api);connect(s,api,db);
 text(s,'Accès par rôle, secrets chiffrés et portail administrateur distinct.',56,614,1110,42,25,C.mute);
}
{
 const s=slide('La validation suit les parcours du produit','Vérification','La validation combine les tests unitaires des détecteurs et de la narration avec des parcours de navigateur exécutés sur une pile locale. Les captures et la vidéo de cette livraison montrent ce qui a été parcouru. Les mesures historiques disposent de leur date et de leur méthode. Un test ignoré ne démontre pas qu’une fonctionnalité fonctionne. Je conserve aussi les limites : connecteurs expérimentaux, charge soutenue et précision des détecteurs. Sources : backend/tests, frontend/playwright, docs/evidence.');
 row(s,'01','Moteur et contrats','Tests de détection, sorties LLM et comportement des connecteurs.',207);
 row(s,'02','Parcours dans le navigateur','Connexion, incident, profil, alertes et gouvernance du prototype.',351);
 row(s,'03','Preuve consultable','Captures de l’application et vidéo issue du scénario local.',495);
}
{
 const s=slide('Démonstration de Panopta','Application',{toString(){return '';}}.toString(),{dark:true});
 text(s,'Une anomalie dans orders',56,219,1100,69,48,C.white,true);
 text(s,'Ouvrir l’incident. Examiner les profils.\nLire l’analyse. Suivre le traitement et l’alerte.',56,328,1130,125,33,'#D8E1DD');
 text(s,'Vidéo locale, sans narration',56,541,1060,37,25,'#A9C1B7');
 const link=text(s,'Demo_Panopta_Mounir_Gaiby.mp4',56,596,1100,41,25,C.white,true);link.text.get('Demo_Panopta_Mounir_Gaiby.mp4').link={uri:'Demo_Panopta_Mounir_Gaiby.mp4',isExternal:true};
 const n='Lancer le fichier Demo_Panopta_Mounir_Gaiby.mp4 placé dans le même dossier que la présentation. La vidéo ne contient pas de narration et utilise des repères français. Elle enregistre l’application locale avec ses données de démonstration. En cas de lien bloqué par PowerPoint, ouvrir directement le MP4 depuis le dossier. Présenter brièvement l’incident avant de lancer la vidéo, puis reprendre sur les limites. Source : vidéo locale et scripts/pfe/record_demo.mjs.';
 s.speakerNotes.textFrame.setText(n);notes[notes.length-1].notes=n;
}
{
 const s=slide('Les limites orientent la suite du travail','Bilan','Le prototype a une chaîne fonctionnelle, mais plusieurs qualités doivent encore être mesurées. Je veux tester la précision des détecteurs sur des scénarios annotés, mesurer la charge avec plusieurs workers, puis consolider la fiabilité des connecteurs selon leur niveau de support. La gouvernance IA reste une extension exploratoire à étendre. L’objectif de la semaine de soutenance est la stabilité de la démonstration. La suite du produit dépasse le calendrier du PFE. Sources : README.md, docs/connector-catalogue.md et docs/ai-governance.md.');
 text(s,'À mesurer',56,219,480,56,34,C.red,true);text(s,'Précision et rappel des détecteurs.\nDébit, concurrence et coût des profils.\nQualité et délai des explications LLM.',56,311,530,202,29,C.ink);
 text(s,'À consolider',710,219,500,56,34,C.red,true);text(s,'Connecteurs expérimentaux.\nExploitation et observabilité.\nGouvernance IA et contrôles de preuve.',710,311,510,202,29,C.ink);
 line(s,56,560,1168);text(s,'Le projet se poursuit après la période de réalisation de juin à août.',56,602,1120,54,26,C.mute);
}
{
 const s=slide('Panopta, un socle pour poursuivre','Conclusion','Ce projet relie l’ingénierie des données, la détection statistique et l’assistance par un modèle de langage. Le résultat principal est une chaîne d’investigation visible dans l’application : les observations conduisent à un incident, l’incident porte une explication et l’équipe dispose d’un suivi. Mon travail chez Oyster a donné un contexte concret à ce besoin de fiabilité. Je vous remercie pour votre attention et je suis prêt à répondre à vos questions.',{dark:true});
 text(s,'Des données observées.\nUne investigation documentée.',56,222,1140,170,57,C.white,true);
 text(s,'Merci pour votre attention',56,492,1100,54,34,'#A9C1B7');text(s,'Mounir Gaiby',56,596,1100,39,25,C.white);
}
// Appendix slides are concise, optional support during questions.
{
 const s=slide('Modèle de données, le cœur du suivi','Réserve A','Ce diagramme simplifié présente le cœur du modèle métier. Une organisation possède des sources. Chaque source expose des tables suivies. Une table possède un historique de profils, des résultats de contrôle et des incidents. Les autres familles couvrent utilisateurs, moniteurs, alertes et gouvernance IA. Le schéma complet est dans le rapport et les migrations Alembic. Source : backend/app/models et docs/pfe/database_evidence.json.');
 const a=box(s,'Organization\nid, slug, plan',56,235,327,104),b=box(s,'DataSource\norg_id, type, config chiffrée',478,235,327,104),c=box(s,'MonitoredTable\nsource_id, cadence',897,235,327,104);connect(s,a,b);connect(s,b,c);
 const d=box(s,'TableProfile\nvolume, fraîcheur, métriques',897,477,327,104),e=box(s,'CheckResult\ntype, statut, observation',478,477,327,104),f=box(s,'Incident\nsévérité, statut, narration',56,477,327,104);connect(s,c,d,'bottom','top');connect(s,d,e,'left','right');connect(s,e,f,'left','right');
 text(s,'Cardinalités principales : une organisation, plusieurs sources et plusieurs historiques.',56,620,1150,38,23,C.mute);
}
{
 const s=slide('Séquence de profilage et d’alerte','Réserve B','Le planificateur envoie une tâche au worker. Le worker appelle le connecteur et conserve le profil. Les contrôles évaluent les signaux et créent ou enrichissent l’incident. La narration et les alertes prolongent ce traitement. Cette vue condense la séquence, avec persistance dans PostgreSQL. Les tâches et branches détaillées figurent dans backend/app/tasks.py. Elle évite de confondre la durée de l’API et celle du fournisseur de langage.');
 const xs=[60,346,632,918], heads=['Planificateur','Worker','Source / base','Narration / alerte'];
 heads.forEach((h,i)=>{box(s,h,xs[i],215,254,54,{size:22});s.shapes.add({geometry:'line',position:{left:xs[i]+127,top:270,width:0,height:326},line:{fill:C.line,width:1}});});
 const seq=[[0,1,'1. Planifier le profil',315],[1,2,'2. Calculer et conserver',390],[2,1,'3. Retour des mesures',465],[1,3,'4. Contrôles, narration, alerte',540]];
 seq.forEach(([a,b,label,y])=>{const left=Math.min(xs[a],xs[b])+127,width=Math.abs(xs[b]-xs[a]);const start=box(s,'',xs[a]+127,y,1,1,{fill:'none'}),end=box(s,'',xs[b]+127,y,1,1,{fill:'none'});connect(s,start,end,a<b?'right':'left',a<b?'left':'right');text(s,label,left+12,y-37,Math.max(width-20,280),32,21,C.ink);});
 text(s,'Les étapes représentent des traitements asynchrones avec résultats persistés.',56,626,1140,34,23,C.mute);
}
{
 const s=slide('Mesures locales de référence','Réserve C','Mesures historiques du 21 août 2026. Trente requêtes séquentielles locales par endpoint après préparation de la pile. Le graphique conserve les p95 en millisecondes : sources 2,59, tables 4,30, incidents 3,91 et santé organisationnelle 144,27. La santé agrège davantage de dimensions. Ces valeurs permettent une comparaison de régression dans un environnement comparable. Elles ne mesurent ni la concurrence, ni la charge soutenue, ni un engagement de service. Source : docs/evidence, release hardening du 21 août, et Notion 7-Day Build Log.');
 const ch=s.charts.add('bar',{position:{left:56,top:219,width:806,height:405},categories:['Sources','Tables','Incidents','Santé organisation'],series:[{name:'p95 (ms)',values:[2.59,4.30,3.91,144.27],fill:C.red}],barOptions:{direction:'bar',grouping:'clustered'},hasLegend:false,dataLabels:{showValue:true,position:'outEnd'},xAxis:{numberFormatCode:'0.0'},chartFill:C.paper,plotAreaFill:C.paper});applyPresentationChartFont(ch,{fontFamily:FONT});
 aside(s,'p95 en ms','30 appels séquentiels\npar endpoint.\n\nMesures locales du\n21 août 2026.');
 text(s,'Repères de régression locale. Charge soutenue et SLA restent à mesurer.',56,642,1130,31,21,C.mute);
}
{
 const s=slide('Les fonctions complémentaires','Réserve D','Les fonctions de collaboration et de reporting donnent au prototype une portée SaaS. Cette capture montre les rapports accessibles dans le produit. Le catalogue de moniteurs, les équipes, les sources et l’administration complètent le parcours. La vidéo fournit une visite plus large de ces fonctions. Si le jury demande un détail, revenir à l’application et distinguer ce qui a été exécuté de ce qui reste expérimental. Sources : frontend/src/pages et captures locales.');
 await screenshot(s,'reports');aside(s,'Au-delà de l’incident','Rapports de fiabilité.\n\nÉquipes et attribution.\n\nMoniteurs et gestion des sources.');
}
{
 const s=slide('Questions techniques à préparer','Réserve E','Pourquoi ce sujet en Big Data et IA ? Il combine traitement de données hétérogènes, profils agrégés et détection statistique ou multivariée, puis narration LLM. Pourquoi pas Kafka ? Le traitement actuel est périodique et repose sur Celery et Redis. Un flux événementiel deviendrait pertinent avec un besoin documenté. Le LLM prouve-t-il la cause ? Non, il produit des hypothèses à vérifier. La gouvernance est-elle complète ? Non, c’est un prototype d’inventaire, de preuves et de contrôles en observation.');
 row(s,'01','Pourquoi plusieurs détecteurs ?','Les règles, les écarts statistiques et les signaux multivariés couvrent des défauts différents.',207);
 row(s,'02','Pourquoi Celery et Redis ?','Le besoin actuel repose sur des tâches périodiques et asynchrones.',351);
 row(s,'03','Que prouve l’IA ?','Elle aide à formuler des hypothèses. L’opérateur vérifie la cause.',495);
}

await fs.writeFile(path.join(tmp,'notes.json'),JSON.stringify(notes,null,2));
await fs.writeFile(path.join(root,'docs/pfe/PRESENTATION_NOTES_FR.md'),'# Panopta, notes de soutenance\n\nPrésentation principale : diapositives 1 à 20. Réserves : 21 à 25.\n\n'+notes.map(n=>`## ${n.slide}. ${n.title}\n\n${n.notes}\n`).join('\n'));
const candidatePath=path.join(tmp,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidatePath);
const result=await finalizePresentation({workspaceDir:root,candidatePath,finalPath,explicitTotalSlideCount:25,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[23],requiredEmbeddedWorkbookChartOwnerSlides:[],materializeLiteralChartWorkbooks:true,nativeChartTargetApplication:'portable',pythonExecutable:process.env.RUNTIME_PYTHON || '/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(tmp,path.basename(finalPath)+'.validation.json')});
console.log(JSON.stringify({finalPath:result.finalPath,slides:p.slides.items.length,integrity:result.packageIntegrity.status,layout:result.presentationLayout.findingCount},null,2));
for(let i=0;i<p.slides.items.length;i++){const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(tmp,`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));}
