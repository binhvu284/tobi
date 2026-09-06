// Lift the CSS out of TOBI_UI_2_SHELL.html and scope every selector under `.ui2`, so the
// shell's design system lands in the app verbatim without touching index.css. The rail, tab
// strip and viewer band are Mission Control's own chrome (or the prototype viewer) and are
// dropped; everything the page itself draws is kept, comments included.
import fs from 'node:fs'

const [,, SHELL, OUT] = process.argv
const html = fs.readFileSync(SHELL, 'utf8')
const css = html.slice(html.indexOf('<style>') + 7, html.indexOf('</style>'))

// Prototype chrome and viewer selectors that do not ship.
const DROP = /^(\.app(?![\w-])|\.rail|\.brand|\.mark(?![\w-])|\.navscroll|\.group(?![\w-])|\.nav(?![\w-])|\.railfoot|\.avatar|\.who(?![\w-])|\.col(?![\w-])|\.strip|\.wtab|\.livepill|\.livedot|\.root|\.proto|\.key(?![\w-])|\.seg(?![\w-])|\.frame|\.view(?![\w-])|\.onlylive|\.onlyboot|html)/

function mapSelector(sel) {
  sel = sel.trim()
  if (!sel) return null
  if (sel === '.app::before') return '.ui2::before'
  if (sel === '.app::after') return '.ui2::after'
  if (DROP.test(sel)) return null
  if (sel === ':root' || sel === 'body') return '.ui2'
  if (sel === '*') return '.ui2 *,.ui2 *::before,.ui2 *::after'
  if (sel === 'button' || sel === 'kbd') return `.ui2 ${sel}`
  if (sel === ':focus-visible') return '.ui2 :focus-visible'
  return `.ui2 ${sel}`
}

// A small CSS walker: rules, @media/@supports (recursed), @keyframes (verbatim), comments kept.
function parse(text) {
  const nodes = []
  let i = 0
  while (i < text.length) {
    if (/\s/.test(text[i])) { let j = i; while (j < text.length && /\s/.test(text[j])) j++; nodes.push({ t: 'raw', s: text.slice(i, j) }); i = j; continue }
    if (text.startsWith('/*', i)) { const j = text.indexOf('*/', i) + 2; nodes.push({ t: 'raw', s: text.slice(i, j) }); i = j; continue }
    const open = text.indexOf('{', i)
    if (open < 0) { nodes.push({ t: 'raw', s: text.slice(i) }); break }
    const head = text.slice(i, open).trim()
    // find the matching close brace
    let depth = 0, j = open
    for (; j < text.length; j++) { if (text[j] === '{') depth++; else if (text[j] === '}') { depth--; if (depth === 0) break } }
    const inner = text.slice(open + 1, j)
    if (head.startsWith('@keyframes')) nodes.push({ t: 'raw', s: text.slice(i, j + 1) })
    else if (head.startsWith('@media') || head.startsWith('@supports')) nodes.push({ t: 'at', head, kids: parse(inner) })
    else nodes.push({ t: 'rule', head, body: inner })
    i = j + 1
  }
  return nodes
}

function emit(nodes) {
  let out = ''
  for (const n of nodes) {
    if (n.t === 'raw') { out += n.s; continue }
    if (n.t === 'at') { const kids = emit(n.kids); if (!kids.trim()) continue; out += `${n.head}{${kids}}`; continue }
    const sels = n.head.split(',').map(mapSelector).filter(Boolean)
    if (!sels.length) continue
    let body = n.body
    if (sels[0] === '.ui2::before') body = body.replace('left:232px', 'left:0')
    out += `${sels.join(',\n')}{${body}}`
  }
  return out
}

const scoped = emit(parse(css))
const header = `/* ══════════════════════════════════════════════════════════════════════════════
   TOBI UI 2.0 — the shell's design system, scoped to the page root.
   GENERATED from docs/feature-idea-queue/TOBI_UI_2_SHELL.html by scripts/ui2_css.mjs:
   every rule is the shell's own, prefixed with .ui2; the prototype's rail, tab strip
   and viewer band are dropped because Mission Control draws its own. Edit the shell
   and regenerate rather than hand-editing this file.
   ══════════════════════════════════════════════════════════════════════════ */
`
const footer = `
/* ── App fit ──────────────────────────────────────────────────────────────────
   The page fills its workspace pane; the scrims and the collapsed canvas sit
   over it, so the root is the positioning context the shell's .app used to be. */
.ui2{position:relative;height:100%;min-height:0;display:flex;flex-direction:column;overflow:hidden;isolation:isolate}
.ui2 .page{flex:1}
.ui2 .console{position:relative;z-index:var(--z-base)}
/* the mono face is self-hosted under its fontsource family name */
.ui2{--mono:"Geist Mono","Geist Mono Variable",ui-monospace,"Cascadia Mono","SF Mono",Consolas,monospace}
/* Mission Control's Motion setting wins over the system preference, as it does everywhere else */
[data-motion="reduced"] .ui2 *,[data-motion="off"] .ui2 *{animation:none!important}

/* ── Small additions the build needed, each named ─────────────────────────
   .modal .acts   the shell's own .acts (folded steps) is a column; a dialog's buttons
                  are the row that justify-content:flex-end was written for.
   .check.failed  a boot check that could not be answered: red, with its reason under the bar.
   .act.ask       a step that asks first (owner decision Q16), amber like the locked microphone.
   :disabled rows a file with nothing to open yet. */
.ui2 .modal .acts{flex-direction:row}
.ui2 .check.failed .st{border-color:rgba(248,81,73,.45);background:rgba(248,81,73,.12);color:var(--bad)}
.ui2 .check.failed .nm{color:var(--text)}
.ui2 .check.failed .val{color:var(--bad)}
.ui2 .bootacts{display:flex;gap:var(--sp-2);margin-top:8px}
.ui2 .act.ask{flex-wrap:wrap;border-color:rgba(210,153,34,.34);background:linear-gradient(180deg,rgba(210,153,34,.10),rgba(210,153,34,.03))}
.ui2 .act.ask > .ic{color:var(--warn)}
.ui2 .act.ask .stat{color:var(--warn)}
.ui2 .act.ask .retry + .retry{margin-left:6px}
.ui2 .rowitem:disabled,.ui2 .fileref:disabled{opacity:.55;cursor:default}
`
fs.writeFileSync(OUT, header + scoped + footer)

// Report the class names this file styles that index.css also styles at rule start, so
// nothing leaks into the page from the app's global sheet.
const mine = new Set([...scoped.matchAll(/\.([a-zA-Z][\w-]*)/g)].map(m => m[1]))
const app = fs.readFileSync(process.argv[4], 'utf8')
const theirs = new Set([...app.matchAll(/(?:^|[,\n}])\s*\.([a-zA-Z][\w-]*)/g)].map(m => m[1]))
const clash = [...mine].filter(c => c !== 'ui2' && theirs.has(c))
console.log(`scoped ${scoped.length} chars; ${mine.size} class names; clashes with index.css: ${clash.length ? clash.join(', ') : 'none'}`)
