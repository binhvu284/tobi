// The documents the shell was designed around, kept verbatim for the demo session so the
// canvas can be checked against the design (foundation plan, burndown, items, script).
// None of this is real data; the scripted driver is the only thing that opens it.
import { Tick } from './icons'
import type { DesignedPane as PaneName, Doc, FileRef, SessionRecap } from './model'

export const DESIGNED_DOCS: Doc[] = [
  { id: 'plan', title: 'foundation-plan.md', kind: 'doc', body: { type: 'designed', pane: 'plan' }, size: '12 KB', at: '09:31' },
  { id: 'burndown', title: 'week-1-burndown.png', kind: 'image', body: { type: 'designed', pane: 'burndown' }, size: '88 KB', at: '09:34' },
  { id: 'items', title: 'week-1-items.csv', kind: 'sheet', body: { type: 'designed', pane: 'items' }, size: '2 KB', at: '09:36' },
  { id: 'scriptdoc', title: 'session-script.md', kind: 'log', body: { type: 'designed', pane: 'scriptdoc' }, size: '9 KB', at: 'live' },
]
export const DEMO_ARTIFACTS: FileRef[] = [
  { id: 'plan', name: 'foundation-plan.md', kind: 'doc', note: 'Edited from the canvas', size: '12 KB', at: '09:31' },
  { id: 'burndown', name: 'week-1-burndown.png', kind: 'image', note: 'Generated from the run log', size: '88 KB', at: '09:34' },
  { id: 'items', name: 'week-1-items.csv', kind: 'sheet', note: 'Four rows, two behind', size: '2 KB', at: '09:36' },
  { id: 'scriptdoc', name: 'session-script.md', kind: 'log', note: 'Written continuously', size: '9 KB', at: 'live' },
]

const at = (daysAgo: number, h: number, m: number) => {
  const d = new Date(); d.setDate(d.getDate() - daysAgo); d.setHours(h, m, 0, 0); return d.toISOString()
}
const recap = (id: string, daysAgo: number, h: number, m: number, secs: number, actions: number, title: string,
  line: string, decisions: string[], open: string[]): SessionRecap => ({
  id, startedAt: at(daysAgo, h, m), endedAt: at(daysAgo, h, m + Math.round(secs / 60)), secs, actions, artifacts: 4,
  title, asked: [], done: [], open, line, decisions,
})
export const DEMO_HISTORY: SessionRecap[] = [
  recap('d1', 0, 9, 12, 31 * 60 + 48, 4, 'Monolith 1 foundation plan, week 1 review',
    'Monolith 1 week one reviewed. Two items behind, both blocked on the same auth callback.',
    ['Week 2 stays as planned. The slip is absorbed inside week 1.', 'The delivery date stays pinned to the contract, page 4.'],
    ['The callback URL still needs registering, and it is the only thing holding both items.']),
  recap('d2', 1, 16, 40, 18 * 60 + 2, 2, 'Client rules read, delivery date pinned to the contract',
    'The client contract binds delivery to 14 days after sign-off.', ['Delivery date pinned to page 4 of client-rules.pdf.'], []),
  recap('d3', 2, 11, 5, 52 * 60 + 19, 9, 'Inbox triage, three runs restarted',
    'Inbox cleared to zero; three stalled runs restarted.', ['Runs restart automatically after a provider outage.'], []),
  recap('d4', 3, 8, 58, 74 * 60, 6, 'Brain V2 curation, first pass',
    'First curation pass over Brain V2 candidates.', ['Filler is never promoted to memory.'], ['Second pass over the sensitive set.']),
]

const Done = ({ children }: { children: string }) => (
  <li className="done"><span className="tick"><Tick className="ic" /></span><span>{children}</span></li>
)
const Todo = ({ children }: { children: string }) => <li><span className="tick" /><span>{children}</span></li>

export function DesignedPane({ pane }: { pane: PaneName }) {
  if (pane === 'plan') return (
    <>
      <h1>Foundation Plan</h1>
      <p className="lede">Six weeks from first commit to the first owner demo. Every week ends with something
        that runs, not something that compiles.</p>
      <div className="meta">
        <span className="chip info">Monolith 1</span>
        <span className="chip">Updated <b className="n">2 days</b> ago</span>
        <span className="chip"><b className="n">12</b> KB</span>
        <span className="chip warn">Week 1, <b className="n">2</b> behind</span>
      </div>
      <h2>Week 1: Skeleton</h2>
      <p>One command brings the whole thing up. Nothing is stubbed that a demo would touch, and the
        seed data is real enough to spot a bad join.</p>
      <ul>
        <Done>Repository, CI, and a green pipeline on an empty test</Done>
        <Done>API and web boot together from one command</Done>
        <Todo>Auth callback route wired end to end</Todo>
        <Todo>Seed dataset that survives a full reset</Todo>
      </ul>
      <pre><span className="c"># boots api + web together, with the seed applied</span>{'\n'}
        <span className="k">$</span> make dev{'\n'}
        <span className="c">→ api  http://localhost:4000   ready in 1.2s</span>{'\n'}
        <span className="c">→ web  http://localhost:5173   ready in 0.8s</span></pre>
      <h2>Week 2: Data layer</h2>
      <p>Schema first, then the queries the demo actually runs. Anything the owner will click gets an
        index before it gets a feature. <code>pnpm db:check</code> must stay green in CI.</p>
      <blockquote>
        <p>The client contract binds delivery to 14 days after sign-off, on page 4 of client-rules.pdf.
          Week 2 is the last week that can absorb a slip without moving that date.</p>
      </blockquote>
      <h2>Week 3: First vertical slice</h2>
      <p>One feature, all the way down: interface, endpoint, table, test. It exists to prove the layers
        fit together, so the feature itself should be the least interesting one on the list.</p>
    </>
  )
  if (pane === 'burndown') return (
    <>
      <h1>Week 1 burndown</h1>
      <p className="lede">Items remaining against the days left in week one. The dashed line is where the
        plan said we would be.</p>
      <div className="meta">
        <span className="chip">Generated <b className="n">09:34</b></span>
        <span className="chip">From the run log</span>
        <span className="chip warn"><b className="n">2</b> behind</span>
      </div>
      <div className="chart">
        <svg viewBox="0 0 200 96" role="img" aria-label="Burndown chart, two items behind plan">
          <path className="grid" d="M18 8h174M18 28h174M18 48h174M18 68h174M18 78h174" />
          <path className="band" d="M18 78 44 66 70 60 96 52 122 46 148 38 148 78z" />
          <path className="ideal" d="M18 78 44 64 70 50 96 36 122 22 148 10" />
          <path className="actual" d="M18 78 44 66 70 60 96 52 122 46 148 38" />
          <circle className="dot" cx="148" cy="38" r="2.4" />
          <text x="0" y="80">0</text><text x="0" y="50">4</text><text x="0" y="11">8</text>
          <text x="14" y="92">Mon</text><text x="66" y="92">Wed</text><text x="118" y="92">Fri</text>
        </svg>
        <div className="legend"><span><i />Done</span><span><i className="ghost" />Planned</span></div>
      </div>
      <p>The gap opens on Wednesday, which is the day the auth callback was meant to land. Nothing
        after it has slipped, so the week still closes on Friday if that one item moves.</p>
    </>
  )
  if (pane === 'items') return (
    <>
      <h1>Week 1 items</h1>
      <p className="lede">The four items in the skeleton week, as they stand right now.</p>
      <div className="meta">
        <span className="chip"><b className="n">4</b> rows</span>
        <span className="chip">Updated <b className="n">09:36</b></span>
      </div>
      <table>
        <thead><tr><th>Item</th><th>Owner</th><th>Due</th><th>State</th></tr></thead>
        <tbody>
          <tr><td>Repository, CI, green pipeline</td><td className="n">TOBI</td><td className="n">Mon</td><td><span className="chip ok">Done</span></td></tr>
          <tr><td>API and web boot from one command</td><td className="n">TOBI</td><td className="n">Tue</td><td><span className="chip ok">Done</span></td></tr>
          <tr><td>Auth callback wired end to end</td><td className="n">Thomas</td><td className="n">Wed</td><td><span className="chip warn">Behind</span></td></tr>
          <tr><td>Seed dataset that survives a reset</td><td className="n">TOBI</td><td className="n">Thu</td><td><span className="chip warn">Behind</span></td></tr>
        </tbody>
      </table>
      <p>Both open items are blocked on the same callback URL. Once that is registered they close
        together, which is why the burndown catches up in one step rather than two.</p>
    </>
  )
  return (
    <>
      <h1>Session script</h1>
      <p className="lede">The written record of this session, as a document you can hand to someone else.</p>
      <div className="meta">
        <span className="chip">Started <b className="n">09:12</b></span>
        <span className="chip"><b className="n">9</b> KB</span>
        <span className="chip live">Still writing</span>
      </div>
      <h2>What was asked</h2>
      <p>Where Monolith 1 stood, then the foundation plan itself, then the two items behind in week one.</p>
      <h2>What was done</h2>
      <ul>
        <Done>Opened the foundation plan on the canvas</Done>
        <Done>Read the run log and drew the week 1 burndown</Done>
        <Done>Exported the four week 1 items</Done>
        <Todo>Register the auth callback URL</Todo>
      </ul>
    </>
  )
}
