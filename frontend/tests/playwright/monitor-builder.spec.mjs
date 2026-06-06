import { chromium } from 'playwright'

const BASE_URL = 'http://acme-corp.localhost:5173'
const API_URL = 'http://localhost:8000'
const TABLE_ID = '3856dac6-46a1-462b-a8ce-f6c1de0d983e'
const SOURCE_ID = '23893dc4-deea-4f2b-83c1-7a9d6553ca80'
const TABLE_URL = `${BASE_URL}/tables/${TABLE_ID}`
const EMAIL = 'mounir@acme.io'
const PASSWORD = 'demo1234'

const unique = Date.now()
const AI_MONITOR_NAME = `PW AI event name monitor ${unique}`
const NL_MONITOR_NAME = `PW NL event name monitor ${unique}`
const GLOBAL_MONITOR_NAME = `PW global event name monitor ${unique}`

async function apiToken() {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ org_slug: 'acme-corp', email: EMAIL, password: PASSWORD }),
  })
  if (!response.ok) throw new Error(`Login failed: ${response.status} ${await response.text()}`)
  return (await response.json()).access_token
}

async function cleanupMonitorNames(names) {
  const token = await apiToken()
  const list = await fetch(`${API_URL}/api/v1/tables/${TABLE_ID}/custom-monitors`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!list.ok) return
  const monitors = await list.json()
  await Promise.all(
    monitors
      .filter((monitor) => names.includes(monitor.name))
      .map((monitor) => fetch(`${API_URL}/api/v1/tables/${TABLE_ID}/custom-monitors/${monitor.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })),
  )
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function login(page) {
  await page.goto(TABLE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForTimeout(1000)
  if ((await page.locator('body').innerText()).includes('Welcome back')) {
    await page.getByLabel('Email address').fill(EMAIL)
    await page.getByLabel('Password').fill(PASSWORD)
    await page.getByRole('button', { name: /sign in/i }).click()
    await page.waitForURL(`${BASE_URL}/`, { timeout: 30000 })
  }
}

async function openTable(page) {
  await page.goto(TABLE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForFunction(() => document.body.innerText.includes('Natural Language Rule Builder'), null, { timeout: 30000 })
  await page.waitForFunction(() => document.body.innerText.includes('Custom SQL Monitors'), null, { timeout: 30000 })
}

async function run() {
  await cleanupMonitorNames([AI_MONITOR_NAME, NL_MONITOR_NAME, GLOBAL_MONITOR_NAME])

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
    await page.route('**/api/v1/sources/*/recommend-monitors', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          table: 'events',
          recommendations: [
            {
              monitor_type: 'null_rate',
              column_name: 'event_name',
              name: AI_MONITOR_NAME,
              rationale: 'Event name is required for analytics and routing.',
              severity: 'P2',
              config: { max_null_rate: 0 },
            },
          ],
          count: 1,
        }),
      })
    })

    await login(page)
    await openTable(page)

    await page.getByRole('button', { name: /^Generate$/ }).first().click()
    await page.waitForFunction((name) => document.body.innerText.includes(name), AI_MONITOR_NAME, { timeout: 30000 })
    const aiCard = page.locator('div.rounded-lg.border').filter({ hasText: AI_MONITOR_NAME }).first()
    await aiCard.getByRole('button', { name: /Add monitor/i }).click()
    await page.waitForFunction((name) => document.body.innerText.includes(name) && document.body.innerText.includes('Custom SQL Monitors'), AI_MONITOR_NAME, { timeout: 30000 })
    await page.waitForFunction((name) => {
      const customIndex = document.body.innerText.indexOf('Custom SQL Monitors')
      const nameIndex = document.body.innerText.lastIndexOf(name)
      return customIndex >= 0 && nameIndex > customIndex
    }, AI_MONITOR_NAME, { timeout: 30000 })

    const nlInput = page.getByPlaceholder('e.g. Paid orders must have a payment reference')
    await nlInput.fill('events must have an event name')
    await page.locator('form', { has: nlInput }).getByRole('button', { name: /^Generate$/ }).click()
    await page.getByLabel('Generated SQL').waitFor({ state: 'visible', timeout: 190000 })
    const sqlTextarea = page.getByLabel('Generated SQL')
    await sqlTextarea.fill('SELECT COUNT(*) FROM public.events WHERE event_name IS NULL')
    await page.getByRole('button', { name: /Test SQL/i }).click()
    await page.waitForFunction(() => /0 violations|\d+ violations? found/i.test(document.body.innerText), null, { timeout: 120000 })
    await page.getByRole('button', { name: /Save as Monitor/i }).click()
    const saveButton = page.getByRole('button', { name: /^Save$/ })
    assert(!(await saveButton.isDisabled()), 'NL save should be enabled after current SQL is tested')
    await page.getByPlaceholder('Monitor name').fill(NL_MONITOR_NAME)
    await saveButton.click()
    await page.waitForFunction((name) => document.body.innerText.includes(name), NL_MONITOR_NAME, { timeout: 30000 })

    await page.goto(`${BASE_URL}/monitors`, { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.waitForFunction(() => document.body.innerText.includes('Monitors'), null, { timeout: 30000 })
    await page.getByRole('button', { name: /Add monitor/i }).first().click()
    await page.getByText('Add Custom SQL Monitor').waitFor({ state: 'visible', timeout: 10000 })
    await page.locator('select').nth(1).selectOption(TABLE_ID)
    await page.getByPlaceholder('e.g. Paid orders without reference').fill(GLOBAL_MONITOR_NAME)
    await page.getByPlaceholder("SELECT COUNT(*) FROM orders WHERE status = 'paid' AND payment_reference IS NULL").fill('SELECT COUNT(*) FROM public.events WHERE event_name IS NULL')
    const createButton = page.getByRole('button', { name: /Create monitor/i })
    assert(await createButton.isDisabled(), 'Global create monitor should be disabled before SQL test')
    await page.getByRole('button', { name: /Test SQL/i }).click()
    await page.waitForFunction(() => /0 violations|\d+ violations? found/i.test(document.body.innerText), null, { timeout: 120000 })
    assert(!(await createButton.isDisabled()), 'Global create monitor should be enabled after SQL test')

    console.log(JSON.stringify({
      status: 'passed',
      checked: ['ai-recommendation-save', 'nl-edit-test-save', 'global-test-before-save'],
      diagnostics,
    }, null, 2))
  } catch (error) {
    await page.screenshot({ path: '/tmp/monitor-builder-failure.png', fullPage: false }).catch(() => {})
    console.error(JSON.stringify({
      status: 'failed',
      message: error.message,
      url: page.url(),
      body: (await page.locator('body').innerText().catch(() => '')).slice(0, 3500),
      diagnostics,
      screenshot: '/tmp/monitor-builder-failure.png',
    }, null, 2))
    process.exitCode = 1
  } finally {
    await browser.close()
    await cleanupMonitorNames([AI_MONITOR_NAME, NL_MONITOR_NAME, GLOBAL_MONITOR_NAME])
  }
}

await run()
