import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'

const workspace = 'http://acme-corp.localhost:5173'
const admin = 'http://admin.localhost:5173'
const output = '../docs/screenshots/pfe'

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 })
page.on('pageerror', (error) => console.error(`pageerror: ${error.message}`))
page.on('console', (message) => {
  if (message.type() === 'error') console.error(`console: ${message.text()}`)
})
await mkdir(output, { recursive: true })

async function settle() {
  await page.waitForLoadState('domcontentloaded')
  await page.waitForTimeout(650)
}

async function capture(name) {
  await page.screenshot({ path: `${output}/${name}.png`, fullPage: true })
  await page.screenshot({ path: `${output}/${name}-report.png`, fullPage: false })
  console.log(`captured ${name}`)
}

async function goto(path, visibleText) {
  await page.goto(`${workspace}${path}`, { waitUntil: 'domcontentloaded' })
  if (visibleText) await page.getByText(visibleText, { exact: true }).first().waitFor({ timeout: 30000 })
  await settle()
}

await page.goto(`${workspace}/login`, { waitUntil: 'domcontentloaded' })
await page.getByText('Welcome back', { exact: true }).waitFor()
await capture('01-workspace-login')

await page.getByLabel('Email address').fill('mounir@acme.io')
await page.getByLabel('Password').fill('demo1234')
await page.getByRole('button', { name: /sign in/i }).click()
await page.waitForURL(`${workspace}/`)
await page.getByRole('heading', { name: 'Operations' }).waitFor()
await settle()
await capture('02-operations')

await goto('/tables', 'Tables')
await capture('03-tables-catalogue')

await goto('/incidents', 'Incidents')
await capture('04-incidents-list')

await page.getByText(/orders.*null rate spiked/i).first().click()
await page.getByText('Key signals').waitFor()
await settle()
const incidentUrl = page.url()
await capture('05-incident-detail')

const aiAnalysis = page.getByText('AI incident analysis', { exact: true })
await aiAnalysis.scrollIntoViewIfNeeded()
await page.waitForTimeout(250)
await capture('06-incident-ai-analysis')

await page.getByText('View table detail', { exact: true }).click()
await page.waitForURL(/\/tables\//)
await page.getByRole('heading', { name: 'public.orders' }).waitFor({ timeout: 60000 })
await settle()
const tableUrl = page.url()
await capture('07-table-orders')

const recommendations = page.getByText('AI recommendations', { exact: true }).first()
if (await recommendations.count()) {
  await recommendations.scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)
  await capture('08-monitor-recommendations')
}

await goto('/monitors', 'Monitors')
await capture('09-monitors-catalogue')
await page.getByRole('button', { name: /new dsl monitor/i }).click()
await page.getByText('New typed DSL monitor', { exact: true }).waitFor()
await capture('10-monitor-builder')
await page.getByRole('button', { name: 'Cancel', exact: true }).click()

await goto('/reports', 'Reports')
await capture('11-weekly-reports')

await goto('/teams', 'Teams')
await capture('12-teams')
await page.getByText('Data Engineering', { exact: true }).first().click()
await page.getByRole('tab', { name: 'Members' }).waitFor()
await capture('13-team-detail')
await page.keyboard.press('Escape')

await goto('/settings?tab=sources', 'Data sources')
await capture('14-data-sources')
await page.getByRole('button', { name: /add source/i }).click()
await page.getByText('Add data source', { exact: true }).waitFor()
await capture('15-connector-catalogue')
await page.getByRole('button', { name: 'Cancel', exact: true }).click()

await goto('/settings?tab=alerts', 'Alert routes')
await page.getByText('pfe-demo@acme.test', { exact: true }).waitFor({ timeout: 30000 })
await capture('16-alert-routes')

await goto('/settings?tab=notifications', 'Email notification preferences')
await capture('17-notification-preferences')

await goto('/ai-systems', 'Governance work queue')
await capture('18-ai-systems')
await page.locator('tbody tr').first().click()
await page.getByText('Declared data map', { exact: true }).waitFor({ timeout: 30000 })
await settle()
await capture('19-ai-governance-detail')
const evidenceTimeline = page.getByText('Evidence timeline', { exact: true })
await evidenceTimeline.scrollIntoViewIfNeeded()
await page.waitForTimeout(250)
await capture('20-ai-evidence-timeline')

await page.goto(`${admin}/login`, { waitUntil: 'domcontentloaded' })
await page.getByText('Staff Access', { exact: true }).waitFor()
await capture('21-staff-login')
await page.getByLabel('Email').fill('admin@datawatch.io')
await page.getByLabel('Password').fill('admin1234')
await page.getByRole('button', { name: /sign in/i }).click()
await page.waitForURL(`${admin}/orgs`)
await page.getByText('Organizations', { exact: true }).waitFor()
await settle()
await capture('22-admin-organizations')

await page.getByRole('link', { name: 'Dashboard', exact: true }).click()
await page.waitForURL(`${admin}/`)
await page.getByRole('heading', { name: 'Admin dashboard' }).waitFor({ timeout: 30000 })
await settle()
await capture('23-admin-dashboard')

await page.getByRole('link', { name: 'Organisations', exact: true }).click()
await page.getByText('Organizations', { exact: true }).waitFor()
const acmeRow = page.locator('tbody tr').filter({ hasText: 'Acme Corp' })
await acmeRow.getByRole('button').click()
await page.getByRole('menuitem', { name: /view details/i }).click()
await page.waitForURL(/\/orgs\/[^/]+$/)
await page.getByRole('heading', { name: 'Acme Corp', exact: true }).waitFor({ timeout: 30000 })
await page.getByText('Organization info', { exact: true }).waitFor({ timeout: 30000 })
await settle()
await capture('24-admin-organization-detail')

await page.goto(incidentUrl, { waitUntil: 'domcontentloaded' })
await page.getByText('Key signals').waitFor()
await page.goto(tableUrl, { waitUntil: 'domcontentloaded' })
await page.getByRole('heading', { name: 'public.orders' }).waitFor()

await browser.close()
console.log(`Captured 24 PFE views in ${output}`)
