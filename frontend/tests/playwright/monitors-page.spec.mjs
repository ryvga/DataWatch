import { chromium } from 'playwright'

const BASE_URL = 'http://acme-corp.localhost:5173'
const API_URL = 'http://localhost:8000'
const EMAIL = 'mounir@acme.io'
const PASSWORD = 'demo1234'
let tokenPromise

async function apiToken() {
  tokenPromise ??= (async () => {
    const response = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ org_slug: 'acme-corp', email: EMAIL, password: PASSWORD }),
    })
    if (!response.ok) throw new Error(`Login failed: ${response.status} ${await response.text()}`)
    return (await response.json()).access_token
  })()
  return tokenPromise
}

async function discoverTableId() {
  const response = await fetch(`${API_URL}/api/v1/tables`, {
    headers: { Authorization: `Bearer ${await apiToken()}` },
  })
  if (!response.ok) throw new Error(`Table discovery failed: ${response.status} ${await response.text()}`)
  const tables = await response.json()
  const table = tables.find((candidate) => candidate.schema_name === 'public' && candidate.table_name === 'orders')
  if (!table) throw new Error('Seeded public.orders table was not found')
  return table.id
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function run() {
  const tableId = await discoverTableId()
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const diagnostics = { consoleErrors: [], pageErrors: [], failedRequests: [], failedResponses: [] }
  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) diagnostics.consoleErrors.push(`${message.type()}: ${message.text()}`)
  })
  page.on('pageerror', (error) => diagnostics.pageErrors.push(error.message))
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText || ''
    if (!failure.includes('ERR_ABORTED')) diagnostics.failedRequests.push(`${request.method()} ${request.url()} ${failure}`)
  })
  page.on('response', async (response) => {
    if (response.status() >= 400 && !response.url().includes('/favicon')) {
      diagnostics.failedResponses.push(`${response.status()} ${response.url()} ${await response.text().catch(() => '')}`)
    }
  })

  try {
    await page.goto(`${BASE_URL}/monitors?table=${tableId}`, { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.waitForTimeout(700)
    if ((await page.locator('body').innerText()).includes('Welcome back')) {
      await page.getByLabel('Email address').fill(EMAIL)
      await page.getByLabel('Password').fill(PASSWORD)
      await page.getByRole('button', { name: /sign in/i }).click()
      await page.waitForURL(`${BASE_URL}/`, { timeout: 30000 })
      await page.goto(`${BASE_URL}/monitors?table=${tableId}`, { waitUntil: 'domcontentloaded', timeout: 30000 })
    }

    const dialog = page.getByRole('dialog', { name: 'New typed DSL monitor' })
    await dialog.waitFor({ state: 'visible', timeout: 30000 })
    await dialog.getByLabel('Monitor name').fill('orders-freshness-e2e')
    await dialog.getByRole('combobox').nth(1).click()
    await page.getByRole('option', { name: 'Freshness · seconds since update' }).click()
    await dialog.getByLabel('Column').fill('created_at')
    await dialog.getByLabel('Breach threshold').fill('3600')
    await dialog.getByRole('button', { name: 'Validate & preview' }).click()
    await dialog.getByText(/Preview valid|Preview compiled/).waitFor({ state: 'visible', timeout: 30000 })
    assert(await dialog.getByRole('textbox', { name: 'DSL definition preview' }).isVisible(), 'DSL definition preview should be visible')
    assert((await dialog.getByRole('button', { name: /Create/ }).count()) === 1, 'DSL create action should be visible after preview')

    console.log(JSON.stringify({ status: 'passed', checked: ['table-to-dsl-builder', 'dsl-preview'], diagnostics }, null, 2))
  } catch (error) {
    await page.screenshot({ path: '/tmp/monitors-page-failure.png', fullPage: false }).catch(() => {})
    console.error(JSON.stringify({
      status: 'failed',
      message: error.message,
      url: page.url(),
      body: (await page.locator('body').innerText().catch(() => '')).slice(0, 4000),
      diagnostics,
      screenshot: '/tmp/monitors-page-failure.png',
    }, null, 2))
    process.exitCode = 1
  } finally {
    await browser.close()
  }
}

await run()
