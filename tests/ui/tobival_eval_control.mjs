import fs from 'node:fs'
import { chromium } from '../../../.agents/skills/playwright-ui-test/node_modules/playwright/index.mjs'

const overview = {
  metrics: {
    ecr: { overall: 92, categories: { policy: 100, routing: 90 }, case_count: 58, source: 'immutable_runtime_eval_evidence' },
    ldr: { value: 41, status: 'available', formula: '0.75 * U + 0.25 * Q', unguarded_decision_share: 42, quality_loss: 38, missing: [] },
  },
  freshness: { latest_suite_at: '2026-08-26T05:00:00Z', latest_suite_id: 'suite-release-1' },
  lanes: {
    strong: { status: 'available', case_count: 58, passed: 57, completion_rate: 98.3 },
    weak: { status: 'available', case_count: 58, passed: 52, completion_rate: 89.7 },
    no_model: { status: 'available', case_count: 34, passed: 33, completion_rate: 97.1 },
  },
  categories: [
    { category: 'policy_approval_security', case_count: 10, passed: 10, pass_rate: 100 },
    { category: 'route_tool_typed_arguments', case_count: 10, passed: 9, pass_rate: 90 },
    { category: 'recovery_idempotency_concurrency', case_count: 10, passed: 10, pass_rate: 100 },
  ],
  workflows: [
    { workflow_id: 'system.status.read', case_count: 6, passed: 6, pass_rate: 100 },
    { workflow_id: 'task.create', case_count: 5, passed: 4, pass_rate: 80 },
    { workflow_id: 'run.recover', case_count: 6, passed: 6, pass_rate: 100 },
  ],
  gates: {
    release: { scope: 'release', allowed: false, required_cases: ['tobival.v1.task-create@1'], passed_cases: [], blockers: ['failed:tobival.v1.task-create@1'] },
    autonomy: { scope: 'autonomy', allowed: true, required_cases: [], passed_cases: [], blockers: [] },
  },
  regressions: [{ case_ref: 'tobival.v1.task-create@1', latest_eval_run_id: 'eval-task-create', status: 'failed' }],
  findings: [{ finding_id: 'finding-task-create', eval_run_id: 'eval-task-create', category: 'policy', severity: 'high', summary: 'Task creation receipt evidence is missing.', remediation_owner: 'runtime', status: 'open', evidence_refs: ['trace:task-create'] }],
  suites: [{ suite_run_id: 'suite-release-1', trigger: 'manual', lane: 'strong', status: 'failed', case_count: 58, capability_refs: ['release'], started_at: '2026-08-26T04:55:00Z', completed_at: '2026-08-26T05:00:00Z' }],
  cases: [
    { eval_case_id: 'tobival.v1.task-create', version: '1', category: 'policy_approval_security', workflow_id: 'task.create', status: 'failed', score: 0.5, threshold: 0.9, completed_at: '2026-08-26T05:00:00Z', release_gate: true, autonomy_gate: true },
    { eval_case_id: 'tobival.v1.system-status', version: '1', category: 'final_answer_grounded_claims', workflow_id: 'system.status.read', status: 'passed', score: 1, threshold: 0.9, completed_at: '2026-08-26T04:59:00Z', release_gate: true, autonomy_gate: false },
  ],
  next_action: 'failed:tobival.v1.task-create@1',
}

const detail = {
  case: { eval_case_id: 'tobival.v1.task-create', version: '1', category: 'policy_approval_security', objective: 'Verify task creation only succeeds with its exact receipt.', scorer: 'structured_evidence', threshold: 0.9, required_evidence: ['receipt_ref', 'project_ref'], release_gate: true, autonomy_gate: true, created_at: '2026-08-26T04:00:00Z' },
  control: { capability_refs: ['workflow:task.create', 'rollout:actions'], freshness_seconds: 86400, sample_eligible: true, created_at: '2026-08-26T04:00:00Z' },
  runs: [{ eval_run_id: 'eval-task-create', status: 'failed', score: 0.5, threshold: 0.9, run_id: 'run-task-create', trace_id: 'trace-task-create', completed_at: '2026-08-26T05:00:00Z', evidence_refs: ['project_ref:project-1', 'trace:task-create'] }],
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
await page.route('**/api/office/stats', route => route.fulfill({ json: {} }))
await page.route('**/api/owner/settings', route => route.fulfill({ json: {} }))
await page.route('**/api/pm/projects', route => route.fulfill({ json: { items: [], total: 0 } }))
await page.route('**/api/evolution', route => route.fulfill({ json: null }))
await page.route('**/api/runtime/evals/cases/**', route => route.fulfill({ json: detail }))
await page.route('**/api/runtime/evals', route => route.fulfill({ json: overview }))
await page.route('**/api/runtime/runs?**', route => route.fulfill({ json: { items: [], next_cursor: null } }))
await page.route('**/api/runtime/loops', route => route.fulfill({ json: { items: [], developer_selection: null } }))
await page.route('**/api/runtime/rollout', route => route.fulfill({ json: { stage: 'shadow', rollback: false, decisions: {} } }))

await page.goto('http://127.0.0.1:4174/runs', { waitUntil: 'networkidle' })
await page.getByRole('tab', { name: 'Evaluations' }).click()
await page.getByText('Eval Control Center').waitFor()
await page.getByText('92%').first().waitFor()
await page.getByText('41%').first().waitFor()
await page.getByRole('button', { name: /tobival.v1.task-create/ }).click()
await page.getByText('Verify task creation only succeeds with its exact receipt.').waitFor()

const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
await page.screenshot({ path: 'artifacts/tobival-eval-desktop.png', fullPage: true })

await page.setViewportSize({ width: 390, height: 844 })
await page.waitForTimeout(200)
const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
await page.screenshot({ path: 'artifacts/tobival-eval-mobile.png', fullPage: true })

console.log(JSON.stringify({ desktopOverflow, mobileOverflow, consoleErrors, failedRequests }, null, 2))
await browser.close()
if (desktopOverflow || mobileOverflow || consoleErrors.length || failedRequests.length) process.exit(1)
