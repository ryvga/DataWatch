import { chromium } from 'playwright'

const BASE_URL = 'http://acme-corp.localhost:5173'
const API_URL = 'http://localhost:8000'
const EMAIL = 'mounir@acme.io'
const PASSWORD = 'demo1234'
const TEST_RECIPIENT = `playwright-alerts-${Date.now()}@example.com`

async function apiToken() {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ org_slug: 'acme-corp', email: EMAIL, password: PASSWORD }),
  })
  if (!response.ok) throw new Error(`Login failed: ${response.status} ${await response.text()}`)
  return (await response.json()).access_token
}

async function cleanupAlerts(recipient) {
  const token = await apiToken()
  const list = await fetch(`${API_URL}/api/v1/alerts`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!list.ok) return
  const alerts = await list.json()
  await Promise.all(
    alerts
      .filter((alert) => alert.channel === 'email' && Array.isArray(alert.config?.to) && alert.config.to.includes(recipient))
      .map((alert) => fetch(`${API_URL}/api/v1/alerts/${alert.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })),
  )
}

async function login(page) {
  await page.goto(`${BASE_URL}/settings?tab=alerts`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForTimeout(1000)
  if ((await page.locator('body').innerText()).includes('Welcome back')) {
    await page.getByLabel('Email address').fill(EMAIL)
    await page.getByLabel('Password').fill(PASSWORD)
    await page.getByRole('button', { name: /sign in/i }).click()
    await page.waitForURL(`${BASE_URL}/`, { timeout: 30000 })
    await page.goto(`${BASE_URL}/settings?tab=alerts`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  }
}

async function run() {
  await cleanupAlerts(TEST_RECIPIENT)

  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const diagnostics = { consoleErrors: [], pageErrors: [], failedRequests: [] }
  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) diagnostics.consoleErrors.push(`${message.type()}: ${message.text()}`)
  })
  page.on('pageerror', (error) => diagnostics.pageErrors.push(error.message))
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText || ''
    if (!failure.includes('ERR_ABORTED')) diagnostics.failedRequests.push(`${request.method()} ${request.url()} ${failure}`)
  })

  try {
    await login(page)
    await page.waitForFunction(() => document.body.innerText.includes('Alert routes'), null, { timeout: 30000 })
    await page.waitForFunction(() => document.body.innerText.includes('PagerDuty') && document.body.innerText.includes('requires Growth'), null, { timeout: 30000 })
    await page.getByRole('button', { name: /Add alert/i }).click()
    await page.getByText('Add alert route').waitFor({ state: 'visible', timeout: 10000 })
    await page.waitForFunction(() => document.body.innerText.includes('All workspace incidents'), null, { timeout: 10000 })
    await page.getByLabel('Recipients').fill(TEST_RECIPIENT)
    await page.getByRole('button', { name: /^Create alert$/ }).click()
    await page.waitForFunction((recipient) => document.body.innerText.includes(recipient), TEST_RECIPIENT, { timeout: 30000 })

    const row = page.locator('tr').filter({ hasText: TEST_RECIPIENT }).first()
    await row.getByRole('button', { name: /Actions for email/i }).click()
    await page.getByRole('menuitem', { name: /Send test/i }).click()
    await page.waitForFunction(() => document.body.innerText.includes('Alert routes'), null, { timeout: 30000 })

    console.log(JSON.stringify({
      status: 'passed',
      checked: ['plan-aware-channel-cards', 'workspace-email-route-create', 'smtp-test-alert'],
      recipient: TEST_RECIPIENT,
      diagnostics,
    }, null, 2))
  } catch (error) {
    await page.screenshot({ path: '/tmp/alerts-regression-failure.png', fullPage: false }).catch(() => {})
    console.error(JSON.stringify({
      status: 'failed',
      message: error.message,
      url: page.url(),
      body: (await page.locator('body').innerText().catch(() => '')).slice(0, 3500),
      diagnostics,
      screenshot: '/tmp/alerts-regression-failure.png',
    }, null, 2))
    process.exitCode = 1
  } finally {
    await browser.close()
    await cleanupAlerts(TEST_RECIPIENT)
  }
}

await run()
