import { chromium } from '../../../.agents/skills/playwright-ui-test/node_modules/playwright/index.mjs'

const baseUrl = process.argv[2] || 'http://127.0.0.1:8090'
const events = [
  ['start', {
    wiring: [],
    suites: [
      { id: 'retry-pass', label: 'Retry passes', package: 'UI', proves: 'The second run passes.' },
      { id: 'retry-fail', label: 'Retry still fails', package: 'UI', proves: 'Both runs fail.' },
    ],
  }],
  ['suite', {
    id: 'retry-pass', label: 'Retry passes', package: 'UI', proves: 'The second run passes.',
    ok: true, checks: 7, failed: 0, detail: '7 checks passed', retried: true, duration_ms: 1200,
  }],
  ['suite', {
    id: 'retry-fail', label: 'Retry still fails', package: 'UI', proves: 'Both runs fail.',
    ok: false, checks: 6, failed: 1, detail: 'FAIL confirmed after retry', retried: true,
    duration_ms: 1400,
  }],
  ['done', {
    summary: { ok: 1, total: 2, checks: 13, failed_ids: ['retry-fail'], flaky_ids: ['retry-pass'] },
  }],
].map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('')

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const consoleErrors = []
const failedRequests = []
page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('requestfailed', request => failedRequests.push(`${request.method()} ${request.url()}`))
page.on('response', response => {
  if (response.status() >= 400) failedRequests.push(`${response.status()} ${response.url()}`)
})

await page.route('**/api/health/infrastructure/stream', route => route.fulfill({
  status: 200,
  contentType: 'text/event-stream',
  body: events,
}))
await page.goto(`${baseUrl}/health?retry-proof=1`, { waitUntil: 'networkidle' })
await page.getByRole('button', { name: 'Infrastructure' }).click()
await page.getByRole('button', { name: 'Run infrastructure test' }).click()
await page.getByText('passed on retry', { exact: true }).waitFor()
await page.getByText('failed twice', { exact: true }).waitFor()
await page.getByText('FAIL confirmed after retry', { exact: true }).waitFor()
await page.screenshot({ path: 'artifacts/health-infrastructure-retry.png', fullPage: true })

console.log(JSON.stringify({
  passedOnRetry: await page.getByText('passed on retry', { exact: true }).count(),
  failedTwice: await page.getByText('failed twice', { exact: true }).count(),
  consoleErrors,
  failedRequests,
}, null, 2))
await browser.close()

if (consoleErrors.length || failedRequests.length) process.exitCode = 1
