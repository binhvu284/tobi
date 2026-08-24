// Morpheus entry point.
//
// Mounted at /morpheus/* OUTSIDE TOBI's AppShell, because Morpheus brings its own sidebar, its
// own tab strip and its own identity. It overrides the Theme v2 CSS variables on its root, so
// every existing Tailwind token class resolves to Morpheus values inside this subtree and TOBI
// values everywhere else -- one design system, two skins, no forked components.
//
// Locked until the gate is passed. Panic lock returns here, to the full arrival, by decision.
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import '@fontsource-variable/geist'
import { MorpheusSessionProvider, useMorpheus } from './MorpheusSession'
import { MorpheusTabsProvider, useMorpheusTabs } from './MorpheusTabsContext'
import MorpheusShell from './MorpheusShell'
import Gate from './Gate'
import Home from './pages/Home'
import Chat from './pages/Chat'
import Osint from './pages/Osint'
import Agents from './pages/Agents'
import Models from './pages/Models'
import AccessLog from './pages/AccessLog'
import Security from './pages/Security'
import ErrorBoundary from '../components/ErrorBoundary'
import { MorpheusFeedbackProvider } from './MorpheusFeedback'
import { MorpheusTerminalProvider, TerminalStandalone } from './MorpheusTerminal'
import { MorpheusCanvasProvider } from './MorpheusCanvas'
import { Grain } from './ui'
import { morpheusStyle } from './tokens'

/**
 * Child paths are RELATIVE, not absolute.
 *
 * This whole app is mounted under `<Route path="/morpheus/*">` in App.tsx, so a nested `<Routes>`
 * resolves against the parent's matched path. Absolute children like "/morpheus/chat" were being
 * looked for at "/morpheus/morpheus/chat" and matched nothing, which rendered every page blank
 * while the shell around them looked perfectly fine. `location` stays absolute -- React Router
 * strips the parent prefix itself.
 */
function RouteSet({ location }: { location?: string }) {
  return (
    <Routes location={location}>
      <Route index element={<Home />} />
      <Route path="chat" element={<Chat />} />
      <Route path="osint" element={<Osint />} />
      <Route path="osint/:objectId" element={<Osint />} />
      <Route path="agents" element={<Agents />} />
      <Route path="models" element={<Models />} />
      <Route path="access" element={<AccessLog />} />
      <Route path="security" element={<Security />} />
      {/* Anything unrecognised lands on Home rather than an empty pane. */}
      <Route path="*" element={<Home />} />
    </Routes>
  )
}

/**
 * One pane per open tab, all mounted. Switching tabs keeps scroll position and in-flight state.
 *
 * `shown` never trusts activeId blindly. If it points at a tab that is not in the list, every
 * pane would be hidden and the owner would get the sidebar and tab strip wrapped around an empty
 * void. Falling back to the first tab means the worst case is the wrong page, not no page.
 */
function TabPanes() {
  const { tabs, activeId } = useMorpheusTabs()
  const shown = tabs.some(t => t.id === activeId) ? activeId : tabs[0]?.id
  return (
    <div className="relative h-full">
      {tabs.map(tab => (
        <section key={tab.id} data-state-key={tab.stateKey}
          className={`absolute inset-0 ${tab.id === shown ? 'block' : 'hidden'}`}>
          <ErrorBoundary key={tab.id}>
            <RouteSet location={tab.route} />
          </ErrorBoundary>
        </section>
      ))}
    </div>
  )
}

function MorpheusBody() {
  const { locked } = useMorpheus()
  const navigate = useNavigate()
  const loc = useLocation()

  if (locked) return <Gate />

  // The console in its own tab gets the whole window: no sidebar, no tab strip. A second monitor
  // showing a shell does not need the rest of the app around it.
  if (loc.pathname === '/morpheus/console') return <TerminalStandalone />

  return (
    <MorpheusTabsProvider>
      <MorpheusShell onExit={() => navigate('/dashboard')}>
        <TabPanes />
      </MorpheusShell>
    </MorpheusTabsProvider>
  )
}

/**
 * Morpheus's motion system, scoped to this subtree.
 *
 * Two jobs.
 *
 * ENTRANCES are CSS rather than JavaScript on purpose: panes for inactive tabs are
 * `display: none`, and a JS animation started against a hidden element can fail to run, leaving
 * content stuck at opacity 0. The un-animated state of `.morph-rise` is the finished state, so
 * the worst case is no animation rather than no page.
 *
 * INTERACTIONS get one shared curve and three durations, applied as a baseline to every control
 * in the app. Before this, each component picked its own duration and easing, so moving across
 * the interface felt subtly uneven -- a 150ms linear-ish button next to a 300ms card next to an
 * untransitioned link. Smoothness is mostly consistency; the individual values matter far less
 * than the fact that everything shares them.
 *
 * The baseline deliberately does NOT include `transform`. Framer writes transforms inline on the
 * elements it drives, and a CSS transition on the same property fights the spring and produces
 * exactly the lag this is meant to remove. Transform transitions stay explicit, per component,
 * on elements the animation library is not touching.
 */
const MORPHEUS_CSS = `
.morph {
  --ease: cubic-bezier(0.32, 0.72, 0, 1);
  --ease-entrance: cubic-bezier(0.16, 1, 0.3, 1);
  --t-fast: 160ms;
  --t: 240ms;
  --t-slow: 340ms;
}

@keyframes morph-rise {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: none; }
}
.morph-rise { animation: morph-rise 0.55s var(--ease-entrance) backwards; }
.morph-word { display: inline-block; animation: morph-rise 0.7s var(--ease-entrance) backwards; }

/* The thinking shimmer: a highlight travelling through the text itself.
   This is the current idiom for "the model is working" precisely because it is quiet. A spinner
   or a pulsing orb competes with the answer that is about to arrive; a moving highlight reads as
   ongoing effort without asking for attention. */
@keyframes morph-shimmer { to { background-position: -200% 0; } }
.morph-shimmer {
  background: linear-gradient(90deg,
    rgb(var(--muted)) 0%, rgb(var(--muted)) 35%,
    rgb(var(--heading)) 50%,
    rgb(var(--muted)) 65%, rgb(var(--muted)) 100%);
  background-size: 200% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: morph-shimmer 2.2s linear infinite;
}

/* A step's marker while its tool is still running. */
@keyframes morph-ping { 0% { transform: scale(1); opacity: 0.55 } 70%, 100% { transform: scale(2.4); opacity: 0 } }
.morph-ping::after {
  content: ""; position: absolute; inset: 0; border-radius: 999px;
  background: currentColor; animation: morph-ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;
}

@media (prefers-reduced-motion: reduce) {
  .morph-shimmer { animation: none; color: rgb(var(--muted)); background: none; -webkit-text-fill-color: currentColor; }
  .morph-ping::after { animation: none; opacity: 0; }
}

/* Baseline smoothing for every control. Components layer transform on top where they need it. */
.morph a,
.morph button,
.morph input,
.morph textarea,
.morph select,
.morph [role="switch"],
.morph [role="tab"],
.morph [role="menuitem"],
.morph [role="option"] {
  transition-property: color, background-color, border-color, box-shadow, opacity, fill, stroke;
  transition-duration: var(--t);
  transition-timing-function: var(--ease);
}

/* Surfaces that lift, tint or reveal on hover. */
.morph .morph-lift {
  transition: transform var(--t) var(--ease), border-color var(--t) var(--ease),
              box-shadow var(--t) var(--ease), background-color var(--t) var(--ease);
}
.morph .morph-lift:hover { transform: translateY(-2px); }
.morph .morph-lift:active { transform: translateY(0); }

/* Icons that respond inside a hovered control, on the same curve as everything else. */
.morph .morph-icon { transition: transform var(--t) var(--ease), color var(--t) var(--ease); }

/* The single gradient in the app, reserved for actions that CREATE something. Defined here
   because ActionButton takes no style prop and a Tailwind arbitrary value containing commas
   does not survive the build. */
.morph .morph-gradient {
  background: linear-gradient(120deg,
    rgb(var(--accent)), rgb(var(--purple)) 45%, rgb(var(--warning)));
}
.morph .morph-gradient:hover { filter: brightness(1.06); }

/* Small controls that lift and press. Adds transform to the baseline, for components that
   cannot take an inline style (ActionButton) and where an arbitrary Tailwind transition with
   commas does not survive the build. */
.morph .morph-tap {
  transition-property: color, background-color, border-color, box-shadow, transform;
  transition-duration: var(--t);
  transition-timing-function: var(--ease);
}

/* Anything that fades in on hover: chevrons, close buttons, source links. */
.morph .morph-reveal { opacity: 0; transition: opacity var(--t) var(--ease); }
.morph :hover > .morph-reveal,
.morph .morph-reveal:focus-visible { opacity: 1; }

.morph [data-scroll] { scroll-behavior: smooth; }

@media (prefers-reduced-motion: reduce) {
  .morph-rise, .morph-word { animation: none; }
  .morph *, .morph *::before, .morph *::after {
    transition-duration: 1ms !important;
    animation-duration: 1ms !important;
  }
  .morph .morph-lift:hover { transform: none; }
}
`

export default function MorpheusApp() {
  return (
    <div style={morpheusStyle}
      className="morph relative h-screen w-full overflow-hidden bg-bg font-sans text-text antialiased">
      <style>{MORPHEUS_CSS}</style>
      <MorpheusSessionProvider>
        <MorpheusFeedbackProvider>
          {/* Canvas outside terminal: the terminal is one kind of thing the canvas holds, and
              asks it to reveal the console rather than owning a window of its own. */}
          <MorpheusCanvasProvider>
            <MorpheusTerminalProvider>
              <MorpheusBody />
              <Grain />
            </MorpheusTerminalProvider>
          </MorpheusCanvasProvider>
        </MorpheusFeedbackProvider>
      </MorpheusSessionProvider>
    </div>
  )
}
