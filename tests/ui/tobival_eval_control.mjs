import fs from 'node:fs'
import { chromium } from '../../../.agents/skills/playwright-ui-test/node_modules/playwright/index.mjs'

const liveBaseUrl = process.argv[2] || null
const baseUrl = liveBaseUrl || 'http://127.0.0.1:4174'
const screenshotPrefix = liveBaseUrl ? 'tobival-eval-live' : 'tobival-eval'

const categoryCounts = {
  final_answer_grounded_claims: 8,
  route_tool_typed_arguments: 10,
  policy_approval_security: 10,
  recovery_idempotency_concurrency: 10,
  brain_context_relevance: 8,
  connector_freshness: 6,
  coding_workflow_qualification: 6,
  cost_budget: 4,
  compatibility_surfaces_model_failure: 10,
}
const workflowCounts = {
  'approval.evaluate': 2, 'brain.recall': 8, 'budget.evaluate': 4,
  'coding.qualify': 6, 'connector.status': 7, 'file.read': 2,
  'policy.evaluate': 7, 'project.list': 3, 'provider.recover': 4,
  'run.recover': 10, 'surface.compatibility': 8, 'system.status.read': 4,
  'task.create': 4, 'terminal.status': 1, 'terminal.typed_command': 2,
}
const artifactCases = Array.from({ length: 72 }, (_, index) => ({
  eval_case_id: index === 0 ? 'tobival.v1.final.status_grounded' : `tobival.v1.case.${index + 1}`,
  version: '1',
  category: index === 0 ? 'final_answer_grounded_claims' : 'route_tool_typed_arguments',
  workflow_id: index === 0 ? 'system.status.read' : 'task.create',
  status: 'passed', score: 1, threshold: 0.9,
  completed_at: '2026-08-26T05:00:00Z', release_gate: true, autonomy_gate: false,
}))

const overview = {
  metrics: {
    ecr: { overall: 100, categories: { policy: 100, routing: 100 }, case_count: 72, source: 'frozen_final_acceptance' },
    ldr: { value: 2.0312, status: 'available', formula: '0.75 * U + 0.25 * Q', unguarded_decision_share: 2.7083, quality_loss: 0, missing: [] },
  },
  freshness: { latest_suite_at: '2026-08-26T05:00:00Z', latest_suite_id: 'suite-release-1' },
  lanes: {
    strong: { status: 'available', case_count: 72, passed: 72, completion_rate: 100 },
    weak: { status: 'available', case_count: 72, passed: 72, completion_rate: 100 },
    no_model: { status: 'available', case_count: 72, passed: 72, completion_rate: 100 },
  },
  categories: Object.entries(categoryCounts).map(([category, case_count]) => ({ category, case_count, passed: case_count, pass_rate: 100 })),
  workflows: Object.entries(workflowCounts).map(([workflow_id, case_count]) => ({ workflow_id, case_count, passed: case_count, pass_rate: 100 })),
  gates: {
    release: { scope: 'release', allowed: false, required_cases: [], passed_cases: [], blockers: ['owner-acceptance-required'] },
    autonomy: { scope: 'autonomy', allowed: true, required_cases: [], passed_cases: [], blockers: [] },
  },
  regressions: [],
  findings: [],
  suites: [{ suite_run_id: 'suite-release-1', trigger: 'manual', lane: 'strong', status: 'passed', case_count: 72, capability_refs: ['release'], started_at: '2026-08-26T04:55:00Z', completed_at: '2026-08-26T05:00:00Z' }],
  cases: artifactCases,
  acceptance: { status: 'ready_for_owner', release_ready: true, case_count: 72, holdout_count: 14, holdout_passed: 14, model_calls: 156, approved_model_call_ceiling: 168, cost_usd: 0, duration_seconds: 484.594 },
  next_action: 'owner-acceptance-required',
}

const detail = {
  case: { eval_case_id: 'tobival.v1.final.status_grounded', version: '1', category: 'final_answer_grounded_claims', workflow_id: 'system.status.read', objective: 'Execute frozen TOBIval case final.status_grounded', scorer: 'structured_evidence', threshold: 0.9, required_evidence: ['projection_ref', 'freshness'], release_gate: true, autonomy_gate: false, created_at: '2026-08-26T04:00:00Z' },
  control: { capability_refs: ['workflow:system.status.read', 'surface:chat'], freshness_seconds: 0, sample_eligible: false, created_at: '2026-08-26T04:00:00Z' },
  runs: ['strong', 'weak', 'no_model'].map(lane => ({ eval_run_id: `eval-status-${lane}`, lane, status: 'passed', score: 1, threshold: 0.9, run_id: null, trace_id: `trace:tobival:v1:${lane}:final.status_grounded`, completed_at: '2026-08-26T05:00:00Z', evidence_refs: ['projection_ref:final.status_grounded', 'freshness:final.status_grounded'] })),
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
await page.getByText('2.0%').first().waitFor()
await page.getByText('Owner acceptance required', { exact: true }).waitFor()
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
