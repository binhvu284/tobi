import fs from 'node:fs'
import { chromium } from '../../../.agents/skills/playwright-ui-test/node_modules/playwright/index.mjs'

const liveBaseUrl = process.argv[2] || null
const baseUrl = liveBaseUrl || 'http://127.0.0.1:4174'
const screenshotPrefix = liveBaseUrl ? 'tobival-eval-live' : 'tobival-eval'
const acceptanceArtifact = JSON.parse(fs.readFileSync('tests/evals/acceptance/final-acceptance.json', 'utf8'))
const manifest = JSON.parse(fs.readFileSync('tests/evals/v1/case_manifest.json', 'utf8'))
const resultRows = new Map(acceptanceArtifact.results.map(row => [`${row.case_id}:${row.lane}`, row]))
const artifactCases = manifest.cases.map(item => {
  const rows = ['strong', 'weak', 'no_model'].map(lane => resultRows.get(`${item.id}:${lane}`))
  if (rows.some(row => !row)) throw new Error(`Final acceptance result missing for ${item.id}`)
  return {
    eval_case_id: `tobival.${acceptanceArtifact.dataset_version}.${item.id}`,
    version: rows[0].version,
    category: item.group,
    workflow_id: item.workflow,
    status: rows.every(row => row.status === 'passed') ? 'passed' : 'failed',
    score: Math.min(...rows.map(row => row.score)),
    threshold: rows[0].threshold,
    completed_at: acceptanceArtifact.generated_at,
    release_gate: true,
    autonomy_gate: item.safety_critical,
  }
})

function progress(key) {
  const groups = new Map()
  for (const item of artifactCases) {
    const name = item[key]
    const values = groups.get(name) || []
    values.push(item)
    groups.set(name, values)
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([name, items]) => {
    const passed = items.filter(item => item.status === 'passed').length
    return { [key]: name, case_count: items.length, passed, pass_rate: 100 * passed / items.length }
  })
}

const overview = {
  metrics: {
    ecr: { ...acceptanceArtifact.metrics.ecr, source: 'canonical_final_acceptance' },
    ldr: { value: acceptanceArtifact.metrics.ldr, status: 'available', formula: acceptanceArtifact.metrics.formula, unguarded_decision_share: acceptanceArtifact.metrics.unguarded_decision_share, quality_loss: acceptanceArtifact.metrics.quality_loss, missing: [] },
  },
  freshness: { latest_suite_at: acceptanceArtifact.generated_at, latest_suite_id: acceptanceArtifact.schema_version },
  lanes: Object.fromEntries(Object.entries(acceptanceArtifact.lanes).map(([lane, row]) => [lane, { status: 'available', case_count: row.case_count, passed: row.passed, completion_rate: row.completion_rate }])),
  categories: progress('category'),
  workflows: progress('workflow_id'),
  gates: {
    release: { scope: 'release', allowed: false, required_cases: [], passed_cases: [], blockers: ['owner-acceptance-required'] },
    autonomy: { scope: 'autonomy', allowed: true, required_cases: [], passed_cases: [], blockers: [] },
  },
  regressions: [],
  findings: [],
  suites: [],
  cases: artifactCases,
  acceptance: { status: 'ready_for_owner', release_ready: acceptanceArtifact.release_ready, evidence_scope: acceptanceArtifact.evidence_scope, generated_at: acceptanceArtifact.generated_at, source_commit: acceptanceArtifact.source_commit, blockers: acceptanceArtifact.blockers, case_count: acceptanceArtifact.case_count, holdout_count: acceptanceArtifact.holdouts.case_count, holdout_passed: acceptanceArtifact.holdouts.passed, model_calls: acceptanceArtifact.model_calls, approved_model_call_ceiling: acceptanceArtifact.approved_model_call_ceiling, cost_usd: acceptanceArtifact.cost_usd, duration_seconds: acceptanceArtifact.duration_seconds, model_quality: acceptanceArtifact.model_quality },
  next_action: 'owner-acceptance-required',
}

const detailCase = manifest.cases.find(item => item.id === 'final.status_grounded')
const detail = {
  case: { eval_case_id: 'tobival.v1.final.status_grounded', version: '1', category: detailCase.group, workflow_id: detailCase.workflow, objective: 'Execute frozen TOBIval case final.status_grounded', scorer: 'structured_evidence', threshold: resultRows.get('final.status_grounded:strong').threshold, required_evidence: detailCase.evidence, release_gate: true, autonomy_gate: detailCase.safety_critical, created_at: acceptanceArtifact.generated_at },
  control: { capability_refs: ['workflow:system.status.read', 'surface:chat'], freshness_seconds: 0, sample_eligible: false, created_at: '2026-08-26T04:00:00Z' },
  runs: ['strong', 'weak', 'no_model'].map(lane => { const row = resultRows.get(`final.status_grounded:${lane}`); return { eval_run_id: `${row.run_id}:${lane}`, lane, status: row.status, score: row.score, threshold: row.threshold, run_id: row.run_id, trace_id: row.trace_ref, completed_at: acceptanceArtifact.generated_at, evidence_refs: row.evidence_refs } }),
  findings: overview.findings,
}

fs.mkdirSync('artifacts', { recursive: true })
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })
const consoleErrors = []
const failedRequests = []
page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
page.on('response', response => { if (response.status() >= 400) failedRequests.push(`${response.status()} ${response.url()}`) })
await page.addInitScript(() => sessionStorage.setItem('tobi.vault.session', 'playwright'))
if (!liveBaseUrl) {
  await page.route('**/api/office/stats', route => route.fulfill({ json: {} }))
  await page.route('**/api/owner/settings', route => route.fulfill({ json: {} }))
  await page.route('**/api/pm/projects', route => route.fulfill({ json: { items: [], total: 0 } }))
  await page.route('**/api/evolution', route => route.fulfill({ json: null }))
  await page.route('**/api/runtime/evals/cases/**', route => route.fulfill({ json: detail }))
  await page.route('**/api/runtime/evals', route => route.fulfill({ json: overview }))
  await page.route('**/api/runtime/runs?**', route => route.fulfill({ json: { items: [], next_cursor: null } }))
  await page.route('**/api/runtime/loops', route => route.fulfill({ json: { items: [], developer_selection: null } }))
  await page.route('**/api/runtime/rollout', route => route.fulfill({ json: { stage: 'shadow', rollback: false, decisions: {} } }))
}

await page.goto(`${baseUrl}/runs`, { waitUntil: 'networkidle' })
await page.getByRole('tab', { name: 'Evaluations' }).click()
await page.getByText('Eval Control Center').waitFor()
await page.getByText('100%').first().waitFor()
await page.getByText('8.8%').first().waitFor()
await page.getByText('Live model proof complete', { exact: true }).waitFor()
await page.getByText('72/72 cases passed', { exact: false }).waitFor()
await page.getByText('156/156 model calls returned', { exact: false }).waitFor()
await page.getByText('model alone passed 32.1%', { exact: false }).waitFor()
await page.getByText('TOBI recovery handled 67.9%', { exact: false }).waitFor()
await page.getByText('Owner acceptance required', { exact: true }).waitFor()
await page.getByText('Categories', { exact: true }).waitFor()
await page.getByText('Workflows', { exact: true }).waitFor()
await page.getByText('Cases 72', { exact: true }).waitFor()
await page.getByRole('button', { name: /tobival.v1.final.status_grounded/ }).click()
await page.getByText('Execute frozen TOBIval case final.status_grounded').waitFor()
await page.getByText('strong - passed', { exact: true }).waitFor()
await page.getByText('weak - passed', { exact: true }).waitFor()
await page.getByText('no model - passed', { exact: true }).waitFor()

const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
await page.screenshot({ path: `artifacts/${screenshotPrefix}-case-detail.png`, fullPage: false })
await page.evaluate(() => {
  window.scrollTo(0, 0)
  document.querySelectorAll('*').forEach(element => { if (element.scrollTop) element.scrollTop = 0 })
})
await page.waitForTimeout(100)
await page.screenshot({ path: `artifacts/${screenshotPrefix}-desktop.png`, fullPage: false })

await page.setViewportSize({ width: 390, height: 844 })
await page.evaluate(() => {
  window.scrollTo(0, 0)
  document.querySelectorAll('*').forEach(element => { if (element.scrollTop) element.scrollTop = 0 })
})
await page.waitForTimeout(200)
const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
await page.screenshot({ path: `artifacts/${screenshotPrefix}-mobile.png`, fullPage: false })

console.log(JSON.stringify({ desktopOverflow, mobileOverflow, consoleErrors, failedRequests }, null, 2))
await browser.close()
if (desktopOverflow || mobileOverflow || consoleErrors.length || failedRequests.length) process.exit(1)
