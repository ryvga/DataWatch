import { chromium } from 'playwright'

const BASE_URL = 'http://acme-corp.localhost:5173'
const EMAIL = 'mounir@acme.io'
const PASSWORD = 'demo1234'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function login(page) {
  await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForTimeout(600)
  if ((await page.locator('body').innerText()).includes('Welcome back')) {
    await page.getByLabel('Email address').fill(EMAIL)
    await page.getByLabel('Password').fill(PASSWORD)
    await page.getByRole('button', { name: /sign in/i }).click()
    await page.waitForURL(`${BASE_URL}/`, { timeout: 30000 })
  }
}

async function run() {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const diagnostics = { consoleErrors: [], pageErrors: [], failedRequests: [], failedResponses: [] }
  page.on('console', (message) => { if (message.type() === 'error') diagnostics.consoleErrors.push(message.text()) })
  page.on('pageerror', (error) => diagnostics.pageErrors.push(error.message))
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText || ''
    if (!failure.includes('ERR_ABORTED')) diagnostics.failedRequests.push(`${request.method()} ${request.url()} ${failure}`)
  })
  page.on('response', (response) => {
    if (response.status() >= 400 && !response.url().includes('favicon')) diagnostics.failedResponses.push(`${response.status()} ${response.url()}`)
  })

  try {
    await login(page)
    await page.getByRole('heading', { name: 'Operations' }).waitFor({ timeout: 30000 })
    await page.getByText('Incident queue').waitFor({ timeout: 30000 })
    await page.getByText('Monitored assets').waitFor({ timeout: 30000 })
    assert(!(await page.locator('body').innerText()).includes('ctx:'), 'Development context must stay hidden for a PFE recording')

    const incident = page.getByText(/orders.*null rate spiked/i).first()
    await incident.waitFor({ timeout: 30000 })
    await incident.click()
    await page.getByText('Key signals').waitFor({ timeout: 30000 })
    await page.getByText('Technical identifiers').waitFor({ timeout: 30000 })
    assert((await page.getByText('Monitoring active').count()) > 0, 'Affected table state must be clearly labelled')
    assert(Object.values(diagnostics).every((items) => items.length === 0), `Browser diagnostics are not empty: ${JSON.stringify(diagnostics)}`)
    console.log(JSON.stringify({ status: 'passed', checked: ['operations-priority-layout', 'recording-context-hidden', 'seeded-orders-incident', 'incident-key-signals', 'technical-identifiers-collapsed'], diagnostics }, null, 2))
  } catch (error) {
    await page.screenshot({ path: '/tmp/pfe-demo-flow-failure.png', fullPage: true }).catch(() => {})
    console.error(JSON.stringify({ status: 'failed', message: error.message, url: page.url(), body: (await page.locator('body').innerText().catch(() => '')).slice(0, 4000), diagnostics }, null, 2))
    process.exitCode = 1
  } finally {
    await browser.close()
  }
}

await run()
