/** English PFE defense V2. One coherent story, with no reserve slides. */
import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..')
const runtime = process.env.RUNTIME_NODE_MODULES || '/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
const require = createRequire(path.join(runtime, '_resolve.cjs'))
const { Presentation, PresentationFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href)
const sharp = require('sharp')
const skill = process.env.PRESENTATION_SKILL_DIR || '/Users/mounir/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.11809/skills/presentations'
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href)

const tmp = path.join(root, 'tmp/pfe/defense-en-v2')
const finalPath = path.resolve(process.argv[2] || path.join(root, 'output/pfe/Presentation_Panopta_PFE_English_V2.pptx'))
await fs.mkdir(tmp, { recursive: true })
await fs.mkdir(path.dirname(finalPath), { recursive: true })

const slides = JSON.parse(await fs.readFile(path.join(root, 'docs/pfe/defense_slides_en.json'), 'utf8'))
const shots = JSON.parse(await fs.readFile(path.join(root, 'docs/pfe/screenshots/demo-2026-09-11/deck-images.json'), 'utf8'))
Object.assign(shots, JSON.parse(await fs.readFile(path.join(root, 'docs/pfe/screenshots/action-2026-09-12/deck-images.json'), 'utf8')))

const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } })
const C = {
  paper: '#F5F2EA',
  ink: '#171C1A',
  muted: '#5F6661',
  red: '#B3203B',
  redSoft: '#EAD1D6',
  green: '#285F50',
  greenSoft: '#D7E2DD',
  dark: '#14211D',
  white: '#FFFFFF',
  line: '#CBCFC9',
  sand: '#E7E0D3',
}
const FONT = 'Arial'

function rect(slide, x, y, width, height, fill, line = 'none', lineWidth = 0) {
  return slide.shapes.add({ geometry: 'rect', position: { left: x, top: y, width, height }, fill, line: { fill: line, width: lineWidth } })
}

function text(slide, value, x, y, width, height, size = 26, color = C.ink, bold = false, align = 'left') {
  const shape = slide.shapes.add({ geometry: 'textbox', position: { left: x, top: y, width, height }, fill: 'none', line: { fill: 'none', width: 0 } })
  shape.text = value
  shape.text.style = {
    typeface: FONT,
    fontSize: size,
    color,
    bold,
    alignment: align,
    verticalAlignment: 'top',
    autoFit: 'none',
    insets: { left: 0, right: 0, top: 0, bottom: 0 },
  }
  return shape
}

function rule(slide, x, y, width, color = C.line, lineWidth = 1) {
  slide.shapes.add({ geometry: 'line', position: { left: x, top: y, width, height: 0 }, line: { fill: color, width: lineWidth } })
}

function node(slide, value, x, y, width, height, options = {}) {
  const shape = rect(slide, x, y, width, height, options.fill || C.white, options.line || C.line, options.lineWidth ?? 1)
  shape.text = value
  shape.text.style = {
    typeface: FONT,
    fontSize: options.size || 22,
    color: options.color || C.ink,
    bold: options.bold ?? true,
    alignment: options.align || 'center',
    verticalAlignment: 'middle',
    autoFit: 'none',
    insets: { left: 12, right: 12, top: 9, bottom: 9 },
  }
  return shape
}

function connect(slide, from, to, fromSide = 'right', toSide = 'left', color = C.red) {
  slide.shapes.connect(from, to, {
    kind: 'elbow',
    fromSide,
    toSide,
    line: { fill: color, width: 2 },
    tail: { type: 'triangle', width: 'sm', length: 'sm' },
  })
}

async function addImage(slide, file, x, y, width, height, alt, fit = 'contain') {
  slide.images.add({
    blob: new Uint8Array(await fs.readFile(path.resolve(root, file))),
    contentType: file.endsWith('.jpg') || file.endsWith('.jpeg') ? 'image/jpeg' : 'image/png',
    alt,
    fit,
    position: { left: x, top: y, width, height },
  })
}

async function preparedScreenshot(key) {
  if (!shots[key]) throw new Error(`Missing screenshot ${key}`)
  const source = path.resolve(root, shots[key])
  const bytes = await fs.readFile(source)
  const crops = {
    connectors_action: { left: 0.245, right: 0.245, top: 0.255, bottom: 0.25 },
    source_discovery: { left: 0.23, right: 0.23, top: 0.18, bottom: 0.32 },
    profile_action: { left: 0.13, right: 0.085, top: 0.045, bottom: 0.14 },
    sql: { left: 0.20, right: 0.105, top: 0.18, bottom: 0.12 },
    dsl: { left: 0.205, right: 0.075, top: 0.055, bottom: 0.24 },
    incident_action: { left: 0.12, right: 0.075, top: 0.03, bottom: 0.20 },
    ai_analysis_action: { left: 0.12, right: 0.075, top: 0.025, bottom: 0.12 },
    governance_action: { left: 0.12, right: 0.01, top: 0.015, bottom: 0.27 },
  }
  const crop = crops[key]
  if (!crop) return bytes
  const meta = await sharp(bytes).metadata()
  return sharp(bytes).extract({
    left: Math.round(meta.width * crop.left),
    top: Math.round(meta.height * crop.top),
    width: Math.floor(meta.width * (1 - crop.left - crop.right)),
    height: Math.floor(meta.height * (1 - crop.top - crop.bottom)),
  }).png().toBuffer()
}

async function screenshotSlide(slide, data) {
  const bytes = await preparedScreenshot(data.key)
  rect(slide, 54, 190, 836, 453, C.white, C.line, 1)
  slide.images.add({
    blob: new Uint8Array(bytes),
    contentType: 'image/png',
    alt: `Real Panopta application screenshot showing ${data.title}`,
    fit: 'contain',
    position: { left: 66, top: 202, width: 812, height: 429 },
  })
  text(slide, data.label, 938, 207, 270, 30, 16, C.red, true)
  rule(slide, 938, 248, 270, C.red, 3)
  text(slide, data.body, 938, 278, 270, 290, 26, C.ink, true)
}

function header(slide, data, index, dark = false) {
  const titleColor = dark ? C.white : C.ink
  const sectionColor = dark ? '#9FB6AD' : C.red
  text(slide, data.section.toUpperCase(), 56, 28, 500, 24, 14, sectionColor, true)
  text(slide, data.title, 56, 64, 1145, 76, 42, titleColor, true)
  rule(slide, 56, 154, 1168, dark ? '#3A4B45' : C.line, 1)
  text(slide, String(index + 1).padStart(2, '0'), 1170, 678, 54, 18, 13, dark ? '#9FB6AD' : C.muted, false, 'right')
}

for (let index = 0; index < slides.length; index += 1) {
  const data = slides[index]
  const slide = deck.slides.add()
  const dark = ['workflow', 'demo', 'conclusion'].includes(data.type)
  slide.background.fill = dark ? C.dark : C.paper
  slide.speakerNotes.textFrame.setText(`SCRIPT\n${data.script}\n\nSOURCES\n${data.sources}`)

  if (data.type === 'cover') {
    rect(slide, 0, 0, 18, 720, C.red)
    await addImage(slide, 'docs/pfe/assets/isga-logo.png', 58, 35, 180, 96, 'ISGA Casablanca logo')
    await addImage(slide, 'docs/pfe/assets/oyster-logo-black.png', 1010, 49, 210, 66, 'Oyster logo')
    rule(slide, 58, 150, 1162, C.red, 2)
    text(slide, 'FINAL-YEAR ENGINEERING PROJECT', 58, 185, 700, 28, 17, C.red, true)
    text(slide, 'Panopta', 52, 226, 1165, 113, 92, C.ink, true)
    text(slide, 'Data quality monitoring and\nAI-assisted incident investigation', 58, 358, 870, 104, 38, C.ink, false)
    text(slide, 'State Engineering Degree in Big Data and Artificial Intelligence', 58, 500, 940, 34, 22, C.muted)
    rule(slide, 58, 580, 1162, C.line, 1)
    text(slide, 'Mounir Gaiby', 58, 611, 300, 28, 21, C.ink, true)
    text(slide, 'Supervised by Pr. HANINE MOHAMED', 424, 611, 500, 28, 21, C.ink)
    text(slide, 'ISGA Casablanca  2025-2026', 910, 611, 310, 28, 20, C.ink, false, 'right')
    continue
  }

  header(slide, data, index, dark)

  if (data.type === 'journey') {
    const items = [
      ['01', 'Context', 'Oyster, problem, objective'],
      ['02', 'Design', 'Architecture, runtime, database'],
      ['03', 'Product flow', 'Sources, tables, monitors, incidents'],
      ['04', 'Evidence', 'Big Data, AI, validation'],
      ['05', 'Demo and conclusion', 'Running application and next work'],
    ]
    items.forEach(([number, label, detail], i) => {
      const y = 192 + i * 88
      text(slide, number, 58, y, 72, 52, 39, i === 2 ? C.red : C.green, true)
      text(slide, label, 150, y + 1, 260, 40, 29, C.ink, true)
      text(slide, detail, 434, y + 6, 745, 36, 25, C.muted)
      if (i < items.length - 1) rule(slide, 150, y + 65, 1028, C.line, 1)
    })
  }

  if (data.type === 'company') {
    await addImage(slide, 'docs/pfe/assets/oyster-logo-black.png', 62, 208, 455, 145, 'Oyster official logo')
    text(slide, 'Software Engineer', 650, 211, 500, 55, 42, C.ink, true)
    text(slide, 'Payments team', 650, 279, 500, 45, 31, C.red, true)
    text(slide, 'Professional employment\ncontext, not an internship', 650, 364, 500, 100, 28, C.muted)
    rule(slide, 58, 522, 1162, C.line, 1)
    text(slide, 'A database can be available while the payment data inside it has already failed.', 58, 562, 1110, 74, 32, C.ink, true)
  }

  if (data.type === 'problem') {
    text(slide, '8,500', 58, 196, 350, 100, 84, C.ink, true)
    text(slide, 'orders returned normally', 58, 296, 440, 44, 28, C.muted)
    text(slide, '100%', 695, 196, 400, 100, 84, C.red, true)
    text(slide, 'payment_status null rate', 695, 296, 460, 44, 28, C.muted)
    rule(slide, 58, 385, 1162, C.line, 1)
    text(slide, 'Infrastructure monitoring sees an available database.', 58, 434, 1110, 46, 31, C.ink)
    text(slide, 'The business sees orders that cannot be trusted.', 58, 505, 1110, 65, 41, C.red, true)
  }

  if (data.type === 'scope') {
    text(slide, 'Panopta turns a data defect into an investigation record.', 58, 196, 1110, 62, 38, C.ink, true)
    rule(slide, 58, 287, 1162, C.red, 3)
    text(slide, 'IN SCOPE', 58, 329, 250, 28, 16, C.red, true)
    text(slide, 'Connect sources\nProfile selected tables\nEvaluate rules and detectors\nOpen incidents and route alerts', 58, 373, 500, 210, 29, C.ink)
    text(slide, 'BOUNDARY', 700, 329, 250, 28, 16, C.red, true)
    text(slide, 'No automatic repair of customer data.\nNo claim that an AI hypothesis proves root cause.\nNo compliance certification.', 700, 373, 480, 190, 29, C.ink)
  }

  if (data.type === 'gantt') {
    const monthX = 390
    const monthWidth = 270
    ;['JUNE', 'JULY', 'AUGUST'].forEach((month, i) => {
      rect(slide, monthX + i * monthWidth, 192, monthWidth - 6, 42, i === 2 ? C.red : C.green)
      text(slide, month, monthX + i * monthWidth, 202, monthWidth - 6, 22, 17, C.white, true, 'center')
    })
    const tasks = [
      ['SaaS foundation and security', 0.0, 0.95],
      ['Sources, profiling, and detectors', 0.55, 1.25],
      ['Typed monitors and incidents', 1.20, 1.10],
      ['Governance, evidence, and report', 1.85, 1.15],
    ]
    tasks.forEach(([label, start, duration], i) => {
      const y = 275 + i * 74
      text(slide, label, 58, y + 4, 305, 50, 23, C.ink, i === 3)
      rule(slide, monthX, y + 36, 804, C.line, 1)
      rect(slide, monthX + start * monthWidth, y, duration * monthWidth, 34, i === 3 ? C.red : C.green)
    })
    text(slide, 'ONGOING AFTER AUGUST', 58, 605, 290, 28, 16, C.red, true)
    text(slide, 'Scale evaluation, production recovery, and continued product development', 390, 601, 800, 34, 24, C.ink)
  }

  if (data.type === 'workflow') {
    const steps = [
      ['01', 'Connect', 'Encrypted source'],
      ['02', 'Discover', 'Schema and table'],
      ['03', 'Profile', 'Compact metrics'],
      ['04', 'Evaluate', 'Rules and models'],
      ['05', 'Investigate', 'Evidence and AI'],
      ['06', 'Respond', 'Owner and alert'],
    ]
    steps.forEach(([number, label, detail], i) => {
      const x = 58 + i * 195
      text(slide, number, x, 220, 160, 46, 34, '#9FB6AD', true)
      text(slide, label, x, 292, 172, 50, 31, C.white, true)
      text(slide, detail, x, 357, 160, 70, 22, '#C9D6D1')
      if (i < steps.length - 1) rule(slide, x + 145, 269, 53, C.red, 3)
    })
    rule(slide, 58, 491, 1162, '#3A4B45', 1)
    text(slide, 'The same order now structures the technical explanation and the product demonstration.', 58, 545, 1110, 70, 31, C.white, true)
  }

  if (data.type === 'architecture') {
    text(slide, 'USER LAYER', 58, 194, 180, 24, 15, C.red, true)
    const ui = node(slide, 'React interface\nJWT workspace session', 58, 230, 286, 92, { fill: C.white, size: 23 })
    text(slide, 'APPLICATION LAYER', 407, 194, 220, 24, 15, C.red, true)
    const api = node(slide, 'FastAPI\nvalidation and tenancy', 407, 230, 286, 92, { fill: C.greenSoft, line: C.green, size: 23 })
    text(slide, 'PERSISTENCE', 936, 194, 200, 24, 15, C.red, true)
    const db = node(slide, 'PostgreSQL\n29 application tables', 936, 230, 286, 92, { fill: C.white, size: 23 })
    connect(slide, ui, api)
    connect(slide, api, db)
    const source = node(slide, 'Data source connectors\nbounded read-only work', 58, 457, 286, 104, { fill: C.white, size: 22 })
    const jobs = node(slide, 'APScheduler, Celery, Redis\nasynchronous execution', 407, 457, 337, 104, { fill: C.dark, line: C.dark, color: C.white, size: 22 })
    const llm = node(slide, 'LLM provider\nstructured incident narration', 936, 457, 286, 104, { fill: C.white, size: 22 })
    connect(slide, api, jobs, 'bottom', 'top')
    connect(slide, jobs, source, 'left', 'right')
    connect(slide, jobs, llm)
    connect(slide, jobs, db, 'right', 'bottom')
    text(slide, 'EXECUTION LAYER', 407, 421, 220, 24, 15, C.red, true)
  }

  if (data.type === 'sequence') {
    const actors = ['API', 'Worker', 'Source connector', 'PostgreSQL']
    const x = [78, 372, 668, 962]
    actors.forEach((actor, i) => {
      node(slide, actor, x[i], 192, 220, 52, { fill: i === 1 ? C.dark : C.white, color: i === 1 ? C.white : C.ink, size: 21 })
      slide.shapes.add({ geometry: 'line', position: { left: x[i] + 110, top: 244, width: 0, height: 382 }, line: { fill: C.line, width: 1 } })
    })
    const messages = [
      [0, 1, '1. Queue profile or monitor run', 276],
      [1, 2, '2. Execute bounded plan', 350],
      [2, 1, '3. Return measurements', 424],
      [1, 3, '4. Persist profile and run', 498],
      [1, 3, '5. Update incident and alerts', 572],
    ]
    messages.forEach(([from, to, label, y]) => {
      const lineY = y + 38
      const start = node(slide, '', x[from] + 110, lineY, 1, 1, { line: 'none' })
      const end = node(slide, '', x[to] + 110, lineY, 1, 1, { line: 'none' })
      connect(slide, start, end, from < to ? 'right' : 'left', from < to ? 'left' : 'right', from === 2 ? C.green : C.red)
      const left = Math.min(x[from], x[to]) + 125
      text(slide, label, left, y, Math.max(Math.abs(x[to] - x[from]) - 28, 260), 34, 18, C.ink, true)
    })
  }

  if (data.type === 'db_domains') {
    text(slide, '29', 58, 192, 180, 104, 82, C.red, true)
    text(slide, 'ORM tables', 58, 290, 210, 40, 27, C.muted)
    const domains = [
      ['7', 'Identity and tenancy', 'organizations, users, roles, keys, invites, teams'],
      ['5', 'Monitoring setup', 'sources, tables, SQL monitors, typed monitors, revisions'],
      ['4', 'Observation and runtime', 'profiles, check results, runs, evaluation state'],
      ['4', 'Operations', 'incidents, alerts, preferences, on-call schedules'],
      ['9', 'AI governance', 'systems, versions, data uses, manifests, evidence, controls'],
    ]
    domains.forEach(([count, label, detail], i) => {
      const y = 183 + i * 91
      text(slide, count, 350, y, 58, 54, 38, i === 4 ? C.red : C.green, true)
      text(slide, label, 430, y + 2, 310, 34, 26, C.ink, true)
      text(slide, detail, 760, y + 5, 446, 52, 21, C.muted)
      if (i < domains.length - 1) rule(slide, 430, y + 65, 776, C.line, 1)
    })
  }

  if (data.type === 'data_model') {
    const org = node(slide, 'Organization', 60, 205, 210, 70, { fill: C.dark, line: C.dark, color: C.white, size: 23 })
    const source = node(slide, 'DataSource', 350, 205, 210, 70, { size: 23 })
    const table = node(slide, 'MonitoredTable', 650, 205, 230, 70, { size: 23 })
    const profile = node(slide, 'TableProfile', 970, 205, 230, 70, { fill: C.greenSoft, line: C.green, size: 23 })
    connect(slide, org, source)
    connect(slide, source, table)
    connect(slide, table, profile)
    const monitor = node(slide, 'Monitor', 60, 434, 210, 70, { size: 23 })
    const revision = node(slide, 'MonitorRevision', 350, 434, 210, 70, { fill: C.greenSoft, line: C.green, size: 23 })
    const run = node(slide, 'MonitorRun', 650, 434, 230, 70, { size: 23 })
    const incident = node(slide, 'Incident', 970, 434, 230, 70, { fill: C.redSoft, line: C.red, size: 23 })
    connect(slide, monitor, revision)
    connect(slide, revision, run)
    connect(slide, run, incident)
    connect(slide, profile, incident, 'bottom', 'top')
    text(slide, 'CONFIGURATION AND OBSERVATION', 60, 300, 460, 24, 15, C.red, true)
    text(slide, 'IMMUTABLE RULE AND EXECUTION HISTORY', 60, 535, 560, 24, 15, C.red, true)
    text(slide, 'CheckResult links each profile to the evidence that can open or update an incident.', 60, 602, 1120, 36, 23, C.muted)
  }

  if (data.type === 'tenancy') {
    const orgA = node(slide, 'Workspace A\nOrganization A', 58, 205, 290, 92, { fill: C.white, size: 22 })
    const orgB = node(slide, 'Workspace B\nOrganization B', 58, 430, 290, 92, { fill: C.white, size: 22 })
    const api = node(slide, 'FastAPI\nresolved organization context', 486, 314, 310, 105, { fill: C.dark, line: C.dark, color: C.white, size: 23 })
    const dataA = node(slide, 'Rows scoped by org_id\nper-organization credentials', 932, 205, 290, 92, { fill: C.greenSoft, line: C.green, size: 21 })
    const dataB = node(slide, 'Rows scoped by org_id\nseparate encrypted config', 932, 430, 290, 92, { fill: C.greenSoft, line: C.green, size: 21 })
    connect(slide, orgA, api)
    connect(slide, orgB, api)
    connect(slide, api, dataA)
    connect(slide, api, dataB)
    text(slide, 'JWT workspace sessions. Role checks. Separate staff portal. HKDF-derived encryption keys.', 58, 596, 1120, 42, 24, C.ink, true)
  }

  if (data.type === 'screenshot') await screenshotSlide(slide, data)

  if (data.type === 'detectors') {
    const methods = [
      ['RULES', 'Empty table\nFreshness breach\nSchema drift', 'Immediate checks'],
      ['Z-SCORE', 'Current metric versus\nrecent profile history', '7 profiles minimum'],
      ['ISOLATION FOREST', 'Multivariate outlier\nacross profile features', '21 profiles minimum'],
      ['STL', 'Seasonal baseline versus\nunexpected residual', '21 daily profiles'],
    ]
    methods.forEach(([name, body, note], i) => {
      const x = i % 2 === 0 ? 58 : 657
      const y = i < 2 ? 195 : 424
      text(slide, name, x, y, 520, 30, 16, C.red, true)
      text(slide, body, x, y + 48, 520, 82, 31, C.ink, true)
      rule(slide, x, y + 148, 510, C.line, 1)
      text(slide, note, x, y + 166, 510, 30, 21, C.muted)
    })
  }

  if (data.type === 'dsl_excerpt') {
    text(slide, 'MEASUREMENT', 58, 197, 440, 26, 15, C.red, true)
    text(slide, 'metric: null_rate\nfield: payment_status', 58, 243, 545, 105, 36, C.ink, true)
    text(slide, 'BREACH CONDITION', 58, 402, 440, 26, 15, C.red, true)
    text(slide, 'null_rate > 0.01', 58, 452, 550, 58, 41, C.red, true)
    rule(slide, 650, 195, 1, C.line, 1)
    text(slide, 'OPERATIONAL POLICY', 716, 197, 440, 26, 15, C.red, true)
    const policies = [
      ['Severity', 'P2'],
      ['Breach', '1 failing run'],
      ['Recovery', '2 passing runs'],
      ['Cooldown', '60 minutes'],
      ['Trigger', 'After each profile'],
    ]
    policies.forEach(([label, value], i) => {
      const y = 250 + i * 68
      text(slide, label, 716, y, 170, 30, 20, C.muted)
      text(slide, value, 904, y, 285, 35, 26, C.ink, true)
      if (i < policies.length - 1) rule(slide, 716, y + 44, 472, C.line, 1)
    })
    text(slide, 'The compiler validates the field against the captured schema before activation.', 58, 602, 1120, 36, 23, C.muted)
  }

  if (data.type === 'response') {
    const pairs = [
      ['alerts_action', 'ALERT ROUTES'],
      ['reports_action', 'REPORTS'],
    ]
    for (let i = 0; i < pairs.length; i += 1) {
      const [key, label] = pairs[i]
      const bytes = await preparedScreenshot(key)
      const x = i === 0 ? 58 : 651
      rect(slide, x, 198, 571, 331, C.white, C.line, 1)
      slide.images.add({ blob: new Uint8Array(bytes), contentType: 'image/png', alt: `Panopta ${label.toLowerCase()} screenshot`, fit: 'contain', position: { left: x + 10, top: 208, width: 551, height: 311 } })
      text(slide, label, x, 552, 260, 28, 16, C.red, true)
    }
    text(slide, 'Detection decides when evidence fails. Routing, ownership, and reporting decide what the team does next.', 58, 603, 1120, 44, 25, C.ink, true)
  }

  if (data.type === 'evidence') {
    const stats = [
      ['67', 'targeted backend tests'],
      ['26', 'validated presentation slides'],
      ['0', 'browser page errors'],
      ['0', 'failed Panopta API responses'],
    ]
    stats.forEach(([value, label], i) => {
      const x = 58 + i * 292
      text(slide, value, x, 190, 250, 92, 72, i < 2 ? C.green : C.red, true)
      text(slide, label, x, 286, 245, 74, 22, C.muted)
    })
    rule(slide, 58, 386, 1162, C.line, 1)
    text(slide, 'BIG DATA', 58, 432, 180, 26, 15, C.red, true)
    text(slide, 'Source-side aggregation and asynchronous connector execution', 58, 473, 505, 80, 27, C.ink, true)
    text(slide, 'ARTIFICIAL INTELLIGENCE', 650, 432, 300, 26, 15, C.red, true)
    text(slide, 'Anomaly detection, structured LLM narration, and evidence-oriented governance', 650, 473, 538, 92, 27, C.ink, true)
    text(slide, 'Local PFE evidence. These numbers are validation results, not production SLA claims.', 58, 610, 1120, 32, 20, C.muted)
  }

  if (data.type === 'demo') {
    text(slide, 'SOURCE', 58, 211, 220, 36, 18, '#9FB6AD', true)
    text(slide, 'TABLE', 288, 211, 220, 36, 18, '#9FB6AD', true)
    text(slide, 'MONITOR', 518, 211, 220, 36, 18, '#9FB6AD', true)
    text(slide, 'INCIDENT', 748, 211, 220, 36, 18, '#9FB6AD', true)
    text(slide, 'RESPONSE', 978, 211, 220, 36, 18, '#9FB6AD', true)
    rule(slide, 58, 273, 1140, C.red, 4)
    text(slide, 'Real local application', 58, 333, 1120, 65, 48, C.white, true)
    text(slide, 'Synthetic e-commerce data. SQL and DSL execution. Incident evidence. AI analysis. Alert delivery. Governance.', 58, 426, 1120, 98, 30, '#C9D6D1')
    const link = text(slide, 'Open Demo_Panopta_PFE_Action.mp4', 58, 580, 720, 40, 24, C.white, true)
    link.text.get('Open Demo_Panopta_PFE_Action.mp4').link = { uri: 'Demo_Panopta_PFE_Action.mp4', isExternal: true }
  }

  if (data.type === 'conclusion') {
    text(slide, 'A source measurement becomes\nan owned investigation.', 58, 207, 1120, 150, 58, C.white, true)
    rule(slide, 58, 398, 1162, C.red, 4)
    text(slide, 'Next work', 58, 446, 250, 34, 18, '#9FB6AD', true)
    text(slide, 'Controlled scale tests. Detector precision and recall.\nProduction recovery. Broader governance evidence.', 58, 492, 1100, 88, 27, C.white)
    text(slide, 'Thank you', 58, 618, 500, 36, 25, '#9FB6AD', true)
  }
}

const totalSeconds = slides.reduce((sum, item) => sum + (item.seconds || 0), 0)
const script = [
  '# Panopta PFE presentation, full English script',
  '',
  ...slides.flatMap((item, index) => [
    `## Slide ${index + 1}. ${item.title}`,
    '',
    item.script,
    '',
  ]),
].join('\n')
await fs.writeFile(path.join(root, 'docs/pfe/PRESENTATION_SCRIPT_EN.md'), script)
await fs.writeFile(path.join(tmp, 'slides.json'), JSON.stringify(slides, null, 2))

const candidatePath = path.join(tmp, 'candidate.pptx')
await (await PresentationFile.exportPptx(deck)).save(candidatePath)
const result = await finalizePresentation({
  workspaceDir: root,
  candidatePath,
  finalPath,
  explicitTotalSlideCount: slides.length,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  pythonExecutable: process.env.RUNTIME_PYTHON || '/Users/mounir/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
  integrityValidatorPath: path.join(skill, 'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(skill, 'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-heading-fit'],
  fontPolicy: { basis: 'design', families: [FONT] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(tmp, `${path.basename(finalPath)}.validation.json`),
})

for (let i = 0; i < deck.slides.items.length; i += 1) {
  const blob = await deck.export({ slide: deck.slides.items[i], format: 'png', scale: 1 })
  await fs.writeFile(path.join(tmp, `slide-${i + 1}.png`), new Uint8Array(await blob.arrayBuffer()))
}

console.log(JSON.stringify({
  finalPath: result.finalPath,
  slides: deck.slides.items.length,
  speakingMinutes: Math.round(totalSeconds / 60),
  integrity: result.packageIntegrity.status,
  layoutFindings: result.presentationLayout.findingCount,
}, null, 2))
