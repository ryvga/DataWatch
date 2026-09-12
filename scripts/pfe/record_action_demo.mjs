/** Real local PFE action recording. FAST=1 rehearses without video. No mocked UI or responses. */
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
const require = createRequire(path.resolve('frontend/package.json'))
const { chromium } = require('playwright')
const out = path.resolve('docs/pfe/screenshots/action-2026-09-12')
const videoDir = path.resolve('tmp/pfe/action-video')
await mkdir(out,{recursive:true}); await mkdir(videoDir,{recursive:true})
const fast = process.env.FAST === '1'
const browser = await chromium.launch({headless:true})
const origin='http://acme-corp.localhost:5173'
const auth = await browser.newContext()
const login = await auth.newPage()
await login.goto(origin+'/login')
await login.getByLabel('Email address').fill('mounir@acme.io')
await login.getByLabel('Password').fill('demo1234')
await login.getByRole('button',{name:/sign in/i}).click()
await login.getByRole('heading',{name:'Operations'}).waitFor()
// Remove only SQL monitors created by earlier rehearsals of this recorder.
await login.getByRole('link').filter({hasText:'public.orders'}).click()
await login.getByText('SQL monitors',{exact:true}).waitFor()
while(await login.getByRole('button',{name:/^Delete Payment status completeness/}).count()){
 await login.getByRole('button',{name:/^Delete Payment status completeness/}).first().click()
 await login.getByRole('button',{name:'Delete monitor',exact:true}).click()
 await login.getByRole('alertdialog').waitFor({state:'hidden'})
}
const state=await auth.storageState(); await auth.close()
const context=await browser.newContext({storageState:state,viewport:{width:1920,height:1080},...(fast?{}:{recordVideo:{dir:videoDir,size:{width:1920,height:1080}}})})
const page=await context.newPage()
const chapters=[], diagnostics={pageErrors:[],responses:[]}
page.on('pageerror',e=>diagnostics.pageErrors.push(e.message))
page.on('response',r=>{if(r.status()>=400&&r.url().startsWith(origin+'/api/v'))diagnostics.responses.push(`${r.status()} ${r.url()}`)})
const start=Date.now(), seconds=()=>(Date.now()-start)/1000
const delay=async(n=650)=>page.waitForTimeout(fast?60:n)
async function click(loc){await loc.scrollIntoViewIfNeeded();const b=await loc.boundingBox();if(b)await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:fast?1:12});await delay(200);await loc.click()}
async function type(loc,text){await click(loc);await loc.fill('');await loc.pressSequentially(text,{delay:fast?0:32})}
async function go(route,text){await page.goto(origin+route,{waitUntil:'domcontentloaded'});await page.getByText(text,{exact:true}).first().waitFor({timeout:45000});await delay(500)}
async function shot(name,caption,narration,action,hold=2.6){const t=seconds();if(action)await action();await delay(500);await page.screenshot({path:path.join(out,name+'.png')});const pause=Math.max(hold,narration.split(/\s+/).length/2.9-(seconds()-t));chapters.push({name,caption,narration,start:t,end:seconds()+ (fast?0:pause),url:page.url()});console.log('Captured '+name);await delay(pause*1000)}
async function see(text){await page.getByText(text,{exact:true}).first().scrollIntoViewIfNeeded();await delay(500)}
async function selectText(text,option){await click(page.getByRole('combobox').filter({hasText:text}).first());await click(page.getByRole('option',{name:option,exact:true}))}
const runName='pfe-payment-completeness-'+Date.now().toString().slice(-6)
const sqlName='Payment status completeness '+runName.slice(-6)
try{
await go('/','Operations')
await shot('01-operations','PANOPTA  /  From a signal to a controlled response','Panopta monitors data quality. This demonstration uses a synthetic e-commerce workspace, not Oyster production data. I will connect the source, inspect a table, and execute two kinds of monitors.',null,4)
await shot('02-source','01  /  Test the live PostgreSQL connection','The source is a live PostgreSQL database. Connection testing checks that Panopta can actually reach it.',async()=>{await go('/settings?tab=sources','Data sources');await click(page.getByRole('button',{name:'Actions for Acme Shop DB (live)'}));await click(page.getByRole('menuitem',{name:'Test connection'}));await delay(1000)},3)
await shot('03-connectors','Capabilities, not interchangeable connector promises','The catalogue exposes different database engines. Support is capability-based, with PostgreSQL as the stable demonstration path.',async()=>{await click(page.getByRole('button',{name:/add source/i}));await page.getByText('Add data source',{exact:true}).waitFor()},2.5)
await click(page.getByRole('button',{name:'Cancel',exact:true}))
await shot('04-discovery','Discover the schema and configure the profiling cadence','Schema discovery supplies the available structure. The monitoring setup also controls the timestamp, cadence, and sensitivity.',async()=>{await go('/settings?tab=tables','Monitored tables');await click(page.getByRole('button',{name:'Add table',exact:true}));await click(page.getByRole('button',{name:'Refresh schema'}));await delay(700);await page.getByPlaceholder('Search discovered tables').fill('orders');await page.getByText('public.orders',{exact:true}).last().click()},3)
await click(page.getByRole('button',{name:'Cancel',exact:true}))
await go('/tables','Tables');await click(page.getByRole('button',{name:'public.orders',exact:true}).last());await page.getByRole('heading',{name:'public.orders'}).waitFor();const tableUrl=page.url()
const tableId=new URL(tableUrl).pathname.split('/').filter(Boolean).at(-1)
await page.evaluate(async(id)=>{
 const token=window.localStorage.getItem('dw_token')
 const response=await fetch(`/api/v1/tables/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify({freshness_column:'created_at'})})
 if(!response.ok)throw new Error(`Unable to prepare the verified schema snapshot: ${response.status} ${await response.text()}`)
},tableId)
await shot('05-profile','02  /  Profile 8,500 orders without exporting the table','The table view brings together volume, freshness, and historical profiles. Aggregates are computed on the source, while snapshots support later comparisons.',null,4)
await shot('06-columns','Filter the columns and inspect completeness','The payment status column is entirely null in this injected scenario. Filtering isolates the evidence instead of scanning every column.',async()=>{await type(page.getByPlaceholder('Filter columns…'),'payment');await delay(400)},3)
await page.getByPlaceholder('Filter columns…').fill('')
await shot('07-built-in','Statistical detectors, ML detectors, and explicit exclusions','Built-in checks combine statistical methods with Isolation Forest and seasonal analysis when enough history exists. Operators can tune checks and exclude columns.',async()=>{await see('Built-in monitors');await click(page.getByRole('button',{name:'shipped_at',exact:true}));await click(page.getByRole('button',{name:'Save changes',exact:true}))},3)
await shot('08-sql-editor','03  /  Write a read-only SQL quality rule','Now I define an explicit business rule. The query counts orders whose payment status is missing, and the monitor runs with each profile.',async()=>{await click(page.getByRole('button',{name:'Add monitor',exact:true}));await type(page.getByPlaceholder('e.g. Paid orders without reference'),sqlName);await type(page.getByPlaceholder('What does this check detect?'),'Detect missing payment status in the order pipeline');await type(page.getByPlaceholder("SELECT COUNT(*) FROM orders WHERE status = 'paid' AND payment_reference IS NULL"),'SELECT COUNT(*) FROM public.orders\nWHERE payment_status IS NULL');await page.getByRole('dialog').locator('select').selectOption('P2')},3)
await shot('09-sql-test','Test SQL  /  Real violation count before saving','The test executes against PostgreSQL and returns the actual violation count. Saving is gated on testing the current query.',async()=>{await click(page.getByRole('button',{name:'Test SQL',exact:true}));await page.getByText(/8500 violations found/).waitFor({timeout:45000})},4)
await shot('10-sql-saved','Save the tested rule and execute it again','The tested SQL becomes a persistent monitor. I can run it immediately as well as on the automatic profiling cadence.',async()=>{await click(page.getByRole('button',{name:'Save monitor',exact:true}));await page.getByRole('dialog').waitFor({state:'hidden'});await see('SQL monitors');const row=page.getByText(sqlName,{exact:true}).last().locator('..');await click(row.getByRole('button').nth(1));await delay(900)},3)
await shot('11-dsl-rule','04  /  Build a typed, schema-bound DSL monitor','The typed DSL is a second approach. I select a completeness metric, bind it to payment status, and define a one-percent breach threshold.',async()=>{await go('/monitors','Monitors');await click(page.getByRole('button',{name:/new dsl monitor/i}));await click(page.locator('#dsl-target'));await click(page.getByRole('option',{name:'public.orders',exact:true}));await type(page.getByLabel('Monitor name',{exact:true}),runName);await selectText('Volume · row count','Completeness · null rate');await type(page.locator('#dsl-metric-field'),'payment_status');await page.locator('#dsl-metric-threshold').fill('0.01')},3)
await shot('12-dsl-policy','Severity, execution mode, cadence, and recovery policy','The policy separates the measurement from operational behavior. Here it uses alert mode, high severity, and the profile trigger, with explicit breach and recovery counts. The definition keeps the default sixty-minute cooldown.',async()=>{await type(page.locator('#dsl-description'),'Missing payment status must remain below 1 percent');await type(page.locator('#dsl-owner'),'Data Engineering');await page.locator('#dsl-breaches').fill('1');await page.locator('#dsl-recovery').fill('2');await page.locator('#dsl-breaches').scrollIntoViewIfNeeded()},3)
await shot('13-dsl-preview','Validate  /  Compile  /  Inspect the immutable definition','Validation checks the schema and connector plan. The canonical JSON and definition hash identify exactly what will be activated.',async()=>{await click(page.getByRole('button',{name:'Validate & preview'}));await page.getByText('Preview compiled and ready to activate',{exact:true}).waitFor({timeout:45000});await page.getByLabel('DSL definition preview').scrollIntoViewIfNeeded()},5)
await shot('14-dsl-active','Activate revision 1, then run the real worker','Activation makes the revision executable. Run now queues the monitor through the actual asynchronous runtime.',async()=>{await click(page.getByRole('button',{name:'Create & activate'}));await page.getByRole('dialog').waitFor({state:'hidden'});const card=page.locator('[data-slot="card"]').filter({hasText:runName});await click(card.getByRole('button',{name:'Run now',exact:true}));await delay(1800);await page.reload();await page.getByText(runName,{exact:true}).waitFor();await delay(600)},4)
await shot('15-run-result','Persist the execution result and its active revision','The table retains the active revision and latest run outcome. This creates a traceable connection between a rule, its execution, and the incident lifecycle.',async()=>{await page.goto(tableUrl);await see('Safe monitor runtime')},4)
await shot('16-profile-run','Trigger a fresh profile and continue the investigation','A manual profile uses the same monitoring pipeline as the scheduler. Processing is asynchronous, so the operator does not need to hold the page open.',async()=>{await page.getByRole('heading',{name:'public.orders'}).scrollIntoViewIfNeeded();await click(page.getByRole('button',{name:'Run now',exact:true}).first());await delay(700)},2)
await shot('17-incidents','05  /  Open the incident and inspect its evidence','The incident connects severity, observed signals, and the affected table. The checks are evidence for investigation, not a diagnosis by themselves.',async()=>{await go('/incidents','Incidents');await page.getByText(/orders.*payment_status null rate spiked/).first().click();await page.getByText('Key signals',{exact:true}).waitFor()},4)
await shot('18-signals','Read the failed checks and the observed measurements','I inspect the failing checks and measurements first. This is how the reviewer can challenge the alert using the underlying observations.',async()=>{await see('Key signals');await page.mouse.wheel(0,420)},3)
await shot('19-ai-analysis','AI explanation  /  Hypotheses, not automatic truth','The language model converts the incident context into a readable explanation. Its probable causes remain hypotheses that a person must verify.',async()=>{await see('AI incident analysis')},5)
await shot('20-actions','Turn the analysis into concrete diagnostic actions','Recommended actions help the engineer choose what to inspect next. The value is operational guidance anchored in the detected signals.',async()=>{await see('Recommended actions')},4)
await shot('21-assignment','Assign ownership without pretending the data is repaired','I assign the investigation to Data Engineering. Acknowledging an incident records ownership. It does not mean the underlying data has recovered.',async()=>{await see('Assignment');await page.locator('select').selectOption({label:'Data Engineering'});const save=page.getByRole('button',{name:'Save assignment',exact:true});if(await save.count())await click(save);const ack=page.getByRole('button',{name:'Acknowledge',exact:true});if(await ack.count())await click(ack)},3)
await shot('22-alerts','06  /  Route alerts by channel and severity','Alert routes carry the incident to the operational team. The local demonstration includes real email delivery.',async()=>{await go('/settings?tab=alerts','Alert routes')},3)
await shot('23-email','An actual alert received in the local mailbox','This message was delivered to the local mailbox. It demonstrates the delivery path without contacting real customers.',async()=>{await page.goto('http://localhost:8025');await page.getByText(/\[Panopta\].*orders/).first().click();await page.getByText('HTML',{exact:true}).waitFor()},3)
await shot('24-reports','Reliability reporting beyond a single incident','Reports summarize the workspace reliability and incident history. They provide the broader view after the detailed investigation.',async()=>{await go('/reports','Reports')},3)
await shot('25-team','Team ownership and notification preferences','Teams structure responsibility. User preferences control how each person receives notifications.',async()=>{await go('/teams','Teams');await click(page.getByText('Data Engineering',{exact:true}).first())},2)
await shot('26-notifications','Delivery preferences remain separate from detection','Notification settings are independent of the underlying detection logic.',async()=>{await go('/settings?tab=notifications','Email notification preferences')},2)
await shot('27-governance','07  /  AI governance is an observe-only prototype','The AI governance area is a small prototype. It tracks declared systems and evidence in observation mode, without claiming certification or automated compliance.',async()=>{await go('/ai-systems','Governance work queue');await page.locator('tbody tr').first().click();await page.getByText('Declared data map',{exact:true}).waitFor()},3)
await shot('28-evidence','Versioned context and an evidence timeline','The evidence timeline makes the declared context inspectable. Extending and validating this prototype remains future work.',async()=>{await see('Evidence timeline')},3)
await shot('29-finish','Measure. Detect. Explain. Act.','The core contribution is this end-to-end chain: source-side profiling, explicit and statistical monitoring, traceable incidents, and assisted investigation.',async()=>{await go('/monitors','Monitors')},4)
}catch(error){await page.screenshot({path:path.join(videoDir,'failure.png')});console.log((await page.locator('body').innerText()).slice(-10000));throw error}finally{const video=page.video();await context.close();const rawVideo=video?await video.path():null;await browser.close();await writeFile(path.join(videoDir,fast?'rehearsal-manifest.json':'recording-manifest.json'),JSON.stringify({recordedAt:new Date().toISOString(),duration:seconds(),rawVideo,chapters,diagnostics},null,2));console.log(JSON.stringify({rawVideo,diagnostics}))}
