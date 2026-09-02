import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'

const base = 'http://acme-corp.localhost:5173'
const output = '../docs/screenshots/pfe'

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 })
await mkdir(output, { recursive: true })

async function capture(name, reportHeight) {
  await page.screenshot({ path: `${output}/${name}.png`, fullPage: true })
  const pageHeight = await page.evaluate(() => document.documentElement.scrollHeight)
  await page.screenshot({
    path: `${output}/${name}-report.png`,
    clip: { x: 0, y: 0, width: 1440, height: Math.min(reportHeight, pageHeight) },
  })
}

await page.goto(base, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(800)
if ((await page.locator('body').innerText()).includes('Welcome back')) {
  await page.getByLabel('Email address').fill('mounir@acme.io')
  await page.getByLabel('Password').fill('demo1234')
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL(`${base}/`)
}

if (page.url().includes('/login')) {
  await page.getByLabel('Email address').fill('mounir@acme.io')
  await page.getByLabel('Password').fill('demo1234')
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL(`${base}/`)
}

await page.getByRole('heading', { name: 'Operations' }).waitFor()
await capture('01-operations', 1100)

await page.getByText(/orders.*null rate spiked/i).first().click()
await page.getByText('Key signals').waitFor()
await capture('02-incident-orders', 1200)

await page.getByText('View table detail', { exact: true }).click()
await page.waitForURL(/\/tables\//)
await page.getByRole('heading', { name: 'public.orders' }).waitFor({ timeout: 60000 })
await capture('03-table-orders', 1250)

await page.goto(`${base}/settings`, { waitUntil: 'networkidle' })
await page.getByRole('button', { name: 'Alerts' }).click()
await page.getByText('pfe-demo@acme.test', { exact: true }).waitFor({ timeout: 30000 })
await capture('04-alerts', 900)

await page.goto(`${base}/ai-systems`, { waitUntil: 'networkidle' })
await page.getByText('Governance work queue').waitFor()
await capture('05-ai-governance', 900)

await browser.close()
console.log(`Captured five PFE screenshots in ${output}`)
