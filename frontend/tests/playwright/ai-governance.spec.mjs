import { chromium } from 'playwright'

const BASE_URL = 'http://acme-corp.localhost:5173'
const SYSTEM_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function login(page) {
  await page.goto(`${BASE_URL}/ai-systems`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForTimeout(600)
  if ((await page.locator('body').innerText()).includes('Welcome back')) {
    await page.getByLabel('Email address').fill('mounir@acme.io')
    await page.getByLabel('Password').fill('demo1234')
    await page.getByRole('button', { name: /sign in/i }).click()
    await page.waitForURL(`${BASE_URL}/`, { timeout: 30000 })
  }
}

const inventory = [{
  id: SYSTEM_ID,
  slug: 'support-rag',
  name: 'Support knowledge assistant',
  lifecycleStatus: 'production',
  currentVersionId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  businessOwnerId: 'owner-1', technicalOwnerId: 'owner-2', riskOwnerId: 'owner-3',
  openFailures: 2,
}]

const detail = {
  ...inventory[0],
  intendedPurpose: 'Answer support questions from approved knowledge articles.',
  prohibitedUses: ['automated account termination'],
  affectedPopulation: 'Support customers',
  autonomyLevel: 'assistive',
  humanOversight: 'Agents approve answers.',
  riskContext: { impact: 'customer-facing' },
  governanceMode: 'observe',
  versions: [{ id: inventory[0].currentVersionId, versionNumber: 1, definitionHash: 'a'.repeat(64), definition: {}, changeRationale: 'Initial release' }],
  deployments: [{ id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', environment: 'production', region: 'ma', status: 'observing', activeManifestId: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', activeManifestHash: 'b'.repeat(64), activationGeneration: 1 }],
  dataUses: [{ id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', versionId: inventory[0].currentVersionId, ordinal: 1, evidenceClass: 'customer_assertion', definitionHash: 'c'.repeat(64), definition: { useKind: 'rag', fields: ['document_id', 'body'], schemaFingerprint: 'd'.repeat(64) } }],
  governanceSummary: {
    headlineStatus: 'action_required',
    inherentRisk: { score: 45, components: { autonomy: 10, production: 20, affectedPopulation: 10, dataSensitivity: 5 } },
    controlCoveragePercent: 100,
    evidenceConfidencePercent: 100,
    residualRiskScore: 37.7,
    reasons: [{ controlId: 'vector-consistency', status: 'fail', reasonCode: 'vector_consistency_violation' }],
  },
  evidenceTimeline: [
    { id: 'eval-1', evidenceId: 'evidence-1', controlId: 'vector-consistency', status: 'fail', evidenceClass: 'connector_observation', reasonCode: 'vector_consistency_violation', inputHash: 'e'.repeat(64), createdAt: '2026-08-21T12:00:00Z' },
    { id: 'eval-2', evidenceId: 'evidence-2', controlId: 'ownership-assertion', status: 'pass', evidenceClass: 'customer_assertion', reasonCode: 'ownership_complete', inputHash: 'f'.repeat(64), createdAt: '2026-08-21T11:59:00Z' },
    { id: 'review-1', controlId: 'release-review', status: 'noted', evidenceClass: 'reviewer_decision', reasonCode: 'reviewer_attestation_recorded', inputHash: '1'.repeat(64), createdAt: '2026-08-21T11:58:00Z' },
  ],
  incidents: [{ id: 'incident-1', controlId: 'vector-consistency', severity: 'P2', status: 'open', title: 'AI governance control failed', createdAt: '2026-08-21T12:00:00Z' }],
}

async function run() {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1280, height: 850 } })
  const diagnostics = { consoleErrors: [], pageErrors: [], failedRequests: [], failedResponses: [] }
  page.on('console', (message) => { if (message.type() === 'error') diagnostics.consoleErrors.push(message.text()) })
  page.on('pageerror', (error) => diagnostics.pageErrors.push(error.message))
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText || ''
    if (!failure.includes('ERR_ABORTED')) diagnostics.failedRequests.push(`${request.method()} ${request.url()} ${failure}`)
  })
  page.on('response', (response) => { if (response.status() >= 400 && !response.url().includes('favicon')) diagnostics.failedResponses.push(`${response.status()} ${response.url()}`) })
  try {
    await login(page)
    await page.route('**/api/v1/ai/systems', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(inventory) }))
    await page.route(`**/api/v1/ai/systems/${SYSTEM_ID}`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(detail) }))
    await page.goto(`${BASE_URL}/ai-systems`, { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.getByText('Governance work queue').waitFor({ timeout: 30000 })
    await page.getByText('Support knowledge assistant').click()
    await page.waitForURL(`${BASE_URL}/ai-systems/${SYSTEM_ID}`, { timeout: 30000 })
    await page.getByText('Declared data map').waitFor({ timeout: 30000 })
    await page.getByText('Evidence timeline').waitFor({ timeout: 30000 })
    await page.getByText('Why this status?').waitFor({ timeout: 30000 })
    assert(await page.getByText('action required').isVisible(), 'Headline governance status must be visible')
    assert(await page.getByText('100%', { exact: true }).first().isVisible(), 'Evidence confidence must be visible')
    assert(await page.getByText(/evidence evidence/).first().isVisible(), 'Evaluations must link to evidence IDs')
    assert(await page.getByText('customer_assertion').first().isVisible(), 'Customer assertions must be visibly labeled')
    assert(await page.getByText('connector_observation').first().isVisible(), 'Connector observations must be visibly labeled')
    assert(await page.getByText('reviewer_decision').first().isVisible(), 'Reviewer decisions must be visibly labeled')
    assert((await page.getByText('Observe only').count()) > 0, 'Observe-only boundary must be visible')
    assert(Object.values(diagnostics).every((items) => items.length === 0), `Browser diagnostics are not empty: ${JSON.stringify(diagnostics)}`)
    console.log(JSON.stringify({ status: 'passed', checked: ['inventory-work-queue', 'system-detail', 'data-map', 'headline-risk-reasons', 'evidence-confidence', 'evidence-provenance', 'observe-only-boundary'], diagnostics }, null, 2))
  } catch (error) {
    await page.screenshot({ path: '/tmp/ai-governance-failure.png', fullPage: true }).catch(() => {})
    console.error(JSON.stringify({ status: 'failed', message: error.message, url: page.url(), body: (await page.locator('body').innerText().catch(() => '')).slice(0, 4000), diagnostics }, null, 2))
    process.exitCode = 1
  } finally {
    await browser.close()
  }
}

await run()
