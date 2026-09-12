/** English PFE deck. Preserves the institutional style of the French delivery. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const root=path.resolve(path.dirname(new URL(import.meta.url).pathname),'../..');
const runtime=process.env.RUNTIME_NODE_MODULES||'/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const require=createRequire(path.join(runtime,'_resolve.cjs'));
const {Presentation,PresentationFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const sharp=require('sharp');
const skill=process.env.PRESENTATION_SKILL_DIR||'/Users/mounir/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.11809/skills/presentations';
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const tmp=path.join(root,'tmp/pfe/defense-en-2026-09-12');
const finalPath=path.resolve(process.argv[2]||path.join(root,'output/pfe/Presentation_Panopta_PFE_English.pptx'));
await fs.mkdir(tmp,{recursive:true});await fs.mkdir(path.dirname(finalPath),{recursive:true});
const slides=JSON.parse(await fs.readFile(path.join(root,'docs/pfe/defense_slides_en.json'),'utf8'));
const shots=JSON.parse(await fs.readFile(path.join(root,'docs/pfe/screenshots/demo-2026-09-11/deck-images.json'),'utf8'));
Object.assign(shots,JSON.parse(await fs.readFile(path.join(root,'docs/pfe/screenshots/action-2026-09-12/deck-images.json'),'utf8')));
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={paper:'#F7F5F0',ink:'#212322',mute:'#626660',red:'#B5233C',line:'#D7D8D1',white:'#FFFFFF',dark:'#192421',green:'#326B59'};
const FONT='Arial';
function text(s,v,x,y,w,h,size=26,color=C.ink,bold=false,align='left'){
 const sh=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text=v;sh.text.style={typeface:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};return sh;
}
function line(s,x,y,w,color=C.line){s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},line:{fill:color,width:1}});}
function box(s,v,x,y,w,h,size=24){const sh=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:C.white,line:{fill:C.line,width:1}});sh.text=v;sh.text.style={typeface:FONT,fontSize:size,color:C.ink,alignment:'center',verticalAlignment:'middle',insets:{left:12,right:12,top:10,bottom:10}};return sh;}
function connect(s,a,b,from='right',to='left'){s.shapes.connect(a,b,{kind:'elbow',fromSide:from,toSide:to,line:{fill:C.red,width:2},tail:{type:'triangle',width:'sm',length:'sm'}});}
async function imageFile(s,file,x,y,w,h,alt){s.images.add({blob:new Uint8Array(await fs.readFile(path.resolve(root,file))),contentType:'image/png',alt,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
async function screenshot(s,key){
 if(!shots[key])throw new Error('Missing real screenshot '+key);
 const bytes=await fs.readFile(path.resolve(root,shots[key]));
 // Crop navigation only where the recorded screenshot has sufficient surrounding space.
 const crops={table:{left:.13,right:.10,top:.05,bottom:.22},narration:{left:.235,right:.305,top:.36,bottom:.21},incident:{left:.23,right:.10,top:.06,bottom:.32},governance:{left:.12,right:.008,top:.015,bottom:.36},reports:{left:.13,right:.10,top:.03,bottom:.25}};
 const actionCrops={source_discovery:{left:.225,right:.235,top:.08,bottom:.08},dsl:{left:.23,right:.11,top:.075,bottom:.32}};
 const isAction=shots[key].includes('action-2026');const crop=isAction?actionCrops[key]:crops[key];const m=await sharp(bytes).metadata();
 const out=crop?await sharp(bytes).extract({left:Math.round(m.width*crop.left),top:Math.round(m.height*crop.top),width:Math.floor(m.width*(1-crop.left-crop.right)),height:Math.floor(m.height*(1-crop.top-crop.bottom))}).png().toBuffer():bytes;
 s.images.add({blob:new Uint8Array(out),contentType:'image/png',alt:'Real Panopta application screenshot: '+key,fit:'contain',position:{left:56,top:205,width:866,height:432}});
}
function rows(s,items){items.forEach(([h,b],i)=>{const y=211+i*145;text(s,String(i+1).padStart(2,'0'),56,y,84,65,50,C.red,true);text(s,h,165,y+2,1030,46,30,C.ink,true);text(s,b,165,y+54,1020,77,25,C.mute);});}
for(let i=0;i<slides.length;i++){
 const d=slides[i],s=p.slides.add(),dark=['demo','conclusion'].includes(d.type);s.background.fill=dark?C.dark:C.paper;
 s.speakerNotes.textFrame.setText(`SAY\n${d.script}\n\nPRESENTER CUE\n${d.cue}\n\nUNDERSTAND\n${d.know}\n\nLIKELY QUESTION\n${d.question}\n${d.answer}\n\nSOURCES\n${d.sources}`);
 if(d.type==='cover'){
  await imageFile(s,'docs/pfe/assets/isga-logo.png',56,32,177,94,'ISGA Casablanca logo');await imageFile(s,'docs/pfe/assets/oyster-logo-black.png',1010,44,212,70,'Oyster logo');
  line(s,56,149,1168,C.red);line(s,56,156,1168,C.red);
  text(s,'FINAL-YEAR ENGINEERING PROJECT',56,196,1100,30,18,C.red,true);text(s,'Panopta',50,244,1170,120,104,C.ink,true);
  text(s,'Data quality monitoring\nand AI-assisted incident investigation',56,381,1150,95,38);
  text(s,'State Engineering Degree\nBig Data and Artificial Intelligence',56,508,1050,64,23,C.mute);
  text(s,'Presented by\nMounir Gaiby',56,619,340,57,20);text(s,'Supervised by\nPr. HANINE MOHAMED',474,619,470,57,20);text(s,'ISGA Casablanca\n2025-2026',1000,619,225,57,20,C.ink,false,'right');continue;
 }
 if(i!==23)text(s,d.section.toUpperCase(),i>=20?100:56,34,1120,25,14,dark?'#A9C1B7':C.red,true);text(s,d.title,56,82,1168,108,44,dark?C.white:C.ink,true);text(s,String(i+1).padStart(2,'0'),1178,678,44,20,13,dark?'#A9C1B7':C.mute,false,'right');
 if(d.type==='rows')rows(s,d.rows);
 if(d.type==='screenshot'){await screenshot(s,d.key);text(s,d.label,952,218,272,72,28,C.red,true);text(s,d.body,952,312,266,313,24);}
 if(d.type==='company'){await imageFile(s,'docs/pfe/assets/oyster-logo-black.png',64,227,460,150,'Oyster official logo');text(s,'Software Engineer\nPayments team',655,219,540,115,40,C.ink,true);text(s,'A professional role.\nA concrete data-reliability problem.',655,369,540,110,27,C.mute);line(s,56,520,1168);text(s,'A payment depends on the quality of the data that describes it.',56,562,1100,90,32);}
 if(d.type==='problem'){text(s,'payment_status',56,219,1110,66,52,C.red,true);text(s,'The database responds.\nPayment statuses are missing.',56,310,1120,128,45,C.ink,true);text(s,'How can an engineer detect the change, inspect the evidence\nand decide what to do next?',56,510,1120,110,30,C.mute);}
 if(d.type==='gantt'){
  const x=420,step=242;['JUNE','JULY','AUGUST'].forEach((m,j)=>text(s,m,x+j*step,214,220,28,21,C.red,true));
  [['Scope and SaaS foundation',0,1],['Connectors and detection',.45,1.4],['Monitors and AI governance',1.2,1.6],['Validation and report',1.7,1.3]].forEach(([h,a,b],j)=>{const y=278+j*76;text(s,h,56,y+7,345,50,24);line(s,x,y+43,726);s.shapes.add({geometry:'rect',position:{left:x+a*step,top:y,width:b*step-10,height:32},fill:j===3?C.red:C.green,line:{fill:'none',width:0}});});
  text(s,'SEPTEMBER AND BEYOND',56,612,360,28,18,C.red,true);text(s,'Demonstration, scale evaluation and continued product development.',420,605,770,60,23);
 }
 if(d.type==='architecture'){
  const ui=box(s,'React interface',56,239,253,84),api=box(s,'FastAPI',384,239,253,84),db=box(s,'PostgreSQL\nProfiles and incidents',929,239,294,84);connect(s,ui,api);connect(s,api,db);
  const jobs=box(s,'Celery + Redis\nBackground execution',384,429,302,100),source=box(s,'Data sources\nConnectors',56,429,253,100),llm=box(s,'LLM provider\nStructured explanation',929,429,294,100);connect(s,api,jobs,'bottom','top');connect(s,jobs,source,'left','right');connect(s,jobs,llm);connect(s,jobs,db,'right','bottom');text(s,'The scheduler triggers profiling according to each table’s cadence.',56,612,1100,40,25,C.mute);
 }
 if(d.type==='sql'){
  text(s,'SELECT COUNT(*) AS violations\nFROM public.orders\nWHERE payment_status IS NULL',56,217,1155,165,37,C.ink,true);line(s,56,406,1168);text(s,'0',56,452,150,90,72,C.green,true);text(s,'No missing status',224,468,490,62,30);text(s,'> 0',56,555,150,90,60,C.red,true);text(s,'Rows to investigate',224,567,490,62,30);text(s,'Source-side calculation.\nOne aggregate result.\nRead-only execution.',822,461,400,170,28,C.mute);
 }
 if(d.type==='detectors'){
  const columns=[['Business rules','Empty table\nFreshness breach\nSchema change','Explicit expectations'],['Statistics','Z-score\nCardinality changes\nVolume growth','Comparison with history'],['ML and time series','Isolation Forest\nSTL decomposition','Enough history required']];
  columns.forEach(([h,b,f],j)=>{const x=[56,472,886][j];text(s,h,x,219,352,75,32,C.red,true);text(s,b,x,316,352,170,29);line(s,x,523,330);text(s,f,x,551,350,90,23,C.mute);});
 }
 if(d.type==='tenancy'){
  const a=box(s,'Organization A\nWorkspace A',56,242,340,106),b=box(s,'Organization B\nWorkspace B',56,430,340,106),api=box(s,'API\nOrganization context',518,323,287,130),db=box(s,'PostgreSQL\nRecords scoped by org_id',928,323,296,130);connect(s,a,api);connect(s,b,api);connect(s,api,db);text(s,'Roles, encrypted source credentials and a separate staff portal.',56,614,1110,42,25,C.mute);
 }
 if(d.type==='demo'){
  text(s,'Monitoring, from setup to investigation',56,219,1130,130,48,C.white,true);text(s,'Source and profiles. SQL and DSL controls.\nExecution, incident evidence and operational response.',56,365,1130,125,32,'#D8E1DD');text(s,'Real local application, synthetic demonstration data',56,541,1130,37,25,'#A9C1B7');const link=text(s,'Demo_Panopta_PFE_Action.mp4',56,596,1100,41,25,C.white,true);link.text.get('Demo_Panopta_PFE_Action.mp4').link={uri:'Demo_Panopta_PFE_Action.mp4',isExternal:true};
 }
 if(d.type==='limits'){
  text(s,'To measure',56,219,480,56,34,C.red,true);text(s,'Detector precision and recall.\nProfile throughput and concurrency.\nLLM quality, cost and latency.',56,311,560,202,29);text(s,'To harden',710,219,500,56,34,C.red,true);text(s,'Experimental connectors.\nProduction operations and recovery.\nAI governance evidence coverage.',710,311,510,202,29);line(s,56,560,1168);text(s,'The project continues beyond the June-to-August PFE development period.',56,602,1130,54,26,C.mute);
 }
 if(d.type==='conclusion'){text(s,'Measured data quality.\nA documented investigation.',56,222,1140,170,57,C.white,true);text(s,'Thank you for your attention',56,492,1100,54,34,'#A9C1B7');text(s,'Mounir Gaiby',56,596,1100,39,25,C.white);}
 if(d.type==='data_model'){
  const a=box(s,'Organization\nid, slug, plan',56,235,327,104),b=box(s,'DataSource\norg_id, type, encrypted config',478,235,327,104),c=box(s,'MonitoredTable\nsource_id, cadence',897,235,327,104);connect(s,a,b);connect(s,b,c);const e=box(s,'TableProfile\nvolume, freshness, metrics',897,477,327,104),f=box(s,'CheckResult\ntype, status, observation',478,477,327,104),g=box(s,'Incident\nseverity, status, narration',56,477,327,104);connect(s,c,e,'bottom','top');connect(s,e,f,'left','right');connect(s,f,g,'left','right');text(s,'One organization owns multiple sources and their monitoring histories.',56,620,1150,38,23,C.mute);
 }
 if(d.type==='sequence'){
  const xs=[60,346,632,918];['User / API','Worker','Source connector','Persistence'].forEach((h,j)=>{box(s,h,xs[j],215,254,54,22);s.shapes.add({geometry:'line',position:{left:xs[j]+127,top:270,width:0,height:326},line:{fill:C.line,width:1}});});
  [[0,1,'1. Queue a pinned revision',315],[1,2,'2. Execute the typed plan',390],[2,1,'3. Return measurements',465],[1,3,'4. Save run and evaluate policy',540]].forEach(([a,b,h,y])=>{const left=Math.min(xs[a],xs[b])+127,w=Math.abs(xs[b]-xs[a]);const v=box(s,'',xs[a]+127,y,1,1),z=box(s,'',xs[b]+127,y,1,1);connect(s,v,z,a<b?'right':'left',a<b?'left':'right');text(s,h,left+12,y-37,Math.max(w-20,285),32,21);});text(s,'Revision identity and run evidence remain available after the execution.',56,626,1140,34,23,C.mute);
 }
 if(d.type==='dsl_excerpt'){
  text(s,'Measurement',56,215,620,42,30,C.red,true);text(s,'metric: null_rate\nfield: payment_status',56,282,650,120,36,C.ink,true);text(s,'Breach condition',56,447,620,42,30,C.red,true);text(s,'null_rate > 0.01',56,512,670,74,41,C.ink,true);text(s,'Operational policy',790,215,420,60,30,C.red,true);text(s,'Severity: P2\nBreach: 1 failing run\nRecovery: 2 passing runs\nCooldown: 60 minutes\nTrigger: on profile',790,300,410,270,27);text(s,'Illustrative excerpt. The full typed document includes identity and schema context.',56,632,1168,32,21,C.mute);
 }
}
const total=slides.slice(0,20).reduce((a,b)=>a+b.seconds,0);
const notes='# Panopta, English slide script and presenter notes\n\nMain presentation: slides 1 to 20. Reserve slides: 21 to 25. Suggested speaking time outside the video: '+Math.round(total/60)+' minutes. Rehearse the actual timed video script separately.\n\nKeep the presentation concise. Read the SAY passages aloud, not the study notes or source references. Pause the video if the jury interrupts.\n\n'+slides.map((d,i)=>`## Slide ${i+1}. ${d.title}\n\n${d.seconds?'Target: '+d.seconds+' seconds.':'Reserve slide, use only when asked.'}\n\n### Say\n\n${d.script}\n\n### Presenter cue\n\n${d.cue}\n\n### Understand before presenting\n\n${d.know}\n\n### Likely jury question\n\n${d.question}\n\n${d.answer}\n\n### Source pointers\n\n${d.sources}\n`).join('\n');
await fs.writeFile(path.join(root,'docs/pfe/PRESENTATION_SCRIPT_EN.md'),notes);
await fs.writeFile(path.join(tmp,'notes.json'),JSON.stringify(slides,null,2));
const candidatePath=path.join(tmp,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidatePath);
const result=await finalizePresentation({workspaceDir:root,candidatePath,finalPath,explicitTotalSlideCount:25,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],pythonExecutable:process.env.RUNTIME_PYTHON||'/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(tmp,path.basename(finalPath)+'.validation.json')});
console.log(JSON.stringify({finalPath:result.finalPath,slides:p.slides.items.length,integrity:result.packageIntegrity.status,layout:result.presentationLayout.findingCount},null,2));
for(let i=0;i<p.slides.items.length;i++){const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(tmp,`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));}
