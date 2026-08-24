// Morpheus session state: locked or open, and the sample data the UI shell renders.
//
// The gate is the whole defence: pass it and everything inside is shown in full. That means
// lock state is the single most important piece of state in this app, so it lives in one place
// that both the gate and the shell's panic button read.
//
// SHELL ONLY. Nothing here talks to a server yet -- `unlock` accepts any input and the records
// below are fixtures, clearly marked, so the surface can be reviewed before the backend exists.
// Real auth replaces `unlock`; real data replaces the fixtures. Neither changes the components.
import {
  createContext, useCallback, useContext, useMemo, useState, type ReactNode,
} from 'react'

export type Factor = 'password' | 'code' | 'key'

/** Which factors the gate demands. Password is not optional; the others are owner toggles. */
export type FactorSettings = { code: boolean; key: boolean }

/**
 * One captured fact about an attempt.
 *
 * `value: null` means the signal was NOT captured, and that is displayed rather than hidden. An
 * absent signal is itself evidence: no mouse movement at all is the difference between a person
 * who mistyped and a script working through a password list, and a log that silently omits empty
 * fields destroys exactly that information.
 */
export type Signal = {
  label: string
  value: string | null
  /** How it compares to the owner's established baseline. */
  verdict?: 'match' | 'mismatch' | 'neutral'
  /** Why this matters, when it is not obvious. */
  note?: string
}

export type SignalGroup = {
  group: string
  kind: 'device' | 'network' | 'behaviour' | 'sequence' | 'context'
  signals: Signal[]
}

/** Morph1's written assessment of an entry. */
export type AgentReport = {
  agent: string
  headline: string
  /** Plain language, no jargon. What happened and what it means. */
  assessment: string[]
  threat: 'none' | 'low' | 'medium' | 'high'
  confidence: number
  intent: string
  predictions: string[]
  recommended: string[]
  generatedAt: string
}

export type AccessEntry = {
  id: string
  at: string
  ok: boolean
  /** Plain-words verdict, a percentage, and the signal breakdown -- all three, by request. */
  verdict: 'you' | 'likely' | 'unknown'
  confidence: number
  attempts: number
  summary: string
  /** The full forensic capture, grouped for reading. */
  groups: SignalGroup[]
  /** Populated once Morph1 has been asked to look at it. */
  report?: AgentReport
  /** Owner judgement, once they have ruled on the entry. */
  ruled?: 'me' | 'not-me'
  blocked?: boolean
}

export type Agent = {
  id: string
  name: string
  role: string
  /** Deactivated agents keep everything; they simply cannot be given work. */
  active: boolean
  status: 'ready' | 'working' | 'idle'
  /** Which model it thinks with. An agent is only as unrestricted as what drives it. */
  model: string
  created: string
  /** One or two lines for the card. */
  description: string
  /** The full account, revealed on expand. */
  detail: string
  skills: string[]
  /** What it is explicitly not allowed to do. Stated, because an agent with hands needs limits. */
  limits: string[]
  runs: number
  lastRun: string | null
}

export type ModelCard = {
  id: string
  name: string
  where: 'local' | 'hosted'
  admitted: boolean
  power: number
  freedom: number
  /** Every number is attributable. No invented figures. */
  source: string
  sourceUrl: string
  license: string
  hardware: string
  note: string
  active?: boolean
}

/**
 * The raw material held about an object.
 *
 * Deliberately open-ended: `kind` drives an icon and nothing else, so a new type of input is one
 * entry in a lookup table rather than a schema change. Everything the profile later claims must
 * be traceable back to one of these, which is why each carries its own timestamp.
 */
export type InputKind =
  | 'name' | 'email' | 'phone' | 'social' | 'link' | 'file' | 'image' | 'location' | 'note'

export type InputItem = {
  id: string
  kind: InputKind
  label: string
  value: string
  /** Where this raw item came from. */
  origin: string
  updatedAt: string
}

/**
 * One line of the compiled profile.
 *
 * `from` is the whole point: a profile field that cannot name the raw items it was built from is
 * an assertion, not a finding. The UI hangs the evidence tooltip off this.
 */
export type ProfileField = {
  id: string
  label: string
  value: string
  from: string[]
  /** Set when the owner has written this themselves rather than the agent deriving it. */
  manual?: boolean
}

export type ProfileSection = { id: string; title: string; fields: ProfileField[] }

export type OsintObject = {
  id: string
  name: string
  kind: 'Domain' | 'Company' | 'Person' | 'IP' | 'URL' | 'File'
  built: string
  sources: number
  confidence: number
  flagged: boolean
  summary: string
  /** Objects can nest, which is what the breadcrumb walks. */
  parentId?: string
  inputs: InputItem[]
  profile: ProfileSection[]
  profileBuiltAt?: string
}

/**
 * Build-phase only.
 *
 * Every page can render four ways -- with data, while loading, with nothing yet, and after a
 * failure. In a finished app three of those are reached by using it. With no backend, they are
 * unreachable, so a reviewer would only ever see the happy path and would sign off on a design
 * that has never been looked at in the states it will actually spend time in.
 *
 * This switch makes all four reachable. It comes out with the first real endpoint.
 */
export type PreviewMode = 'live' | 'loading' | 'empty' | 'failure'

/**
 * Morph1's readings.
 *
 * SHELL ONLY: written out rather than produced by a model, so the report format can be reviewed
 * before the agent exists. The shape is what matters -- what happened, what it means, what is
 * likely next, and what the owner can do -- and a real agent fills the same fields.
 *
 * Register rule: no jargon. "Rented server space" rather than "datacenter ASN", every time.
 */
const REPORTS: Record<string, AgentReport> = {
  a1: {
    agent: 'Morph1', headline: 'This was you, and nothing about it is unusual.',
    threat: 'none', confidence: 99, generatedAt: 'Just now',
    intent: 'Normal use.',
    assessment: [
      'Every signal lines up with how you normally get in. Your own machine, your own home '
      + 'connection, your usual typing speed, and your hardware key physically plugged in.',
      'You opened it in one attempt and passed all three checks in eleven seconds. There is '
      + 'nothing here worth a second look.',
    ],
    predictions: ['Nothing to expect. This is your baseline.'],
    recommended: ['No action needed.'],
  },
  a2: {
    agent: 'Morph1', headline: 'Almost certainly you, with one mistyped password.',
    threat: 'none', confidence: 94, generatedAt: 'Just now',
    intent: 'Normal use, late at night.',
    assessment: [
      'Same machine, same connection, same fingerprint as always. The password was mistyped once '
      + 'and corrected on the second go, with a four second pause in between, which is how a '
      + 'person behaves and not how a program does.',
      'Your typing was slower than usual, which fits the hour rather than a different pair of '
      + 'hands. The only thing missing was your hardware key, because it was not plugged in.',
    ],
    predictions: [
      'If you keep opening it late without the key, more of these will look slightly off your baseline.',
    ],
    recommended: [
      'Nothing urgent. Plug the key in if you want the strongest check on late sessions.',
    ],
  },
  a3: {
    agent: 'Morph1', headline: 'Not a person. This was a program working through stolen passwords.',
    threat: 'high', confidence: 96, generatedAt: 'Just now',
    intent: 'Trying passwords leaked from other services to see whether you reused one here.',
    assessment: [
      'Three things settle it. The mouse never moved once, no key was ever physically held down, '
      + 'and the password was pasted in whole on all five attempts. A human being cannot do that.',
      'The attempts came 1.2 seconds apart, near-identical each time. People do not retry with '
      + 'stopwatch precision, and nobody types five different passwords without a single correction.',
      'The connection came from rented server space in the Netherlands, through a commercial VPN, '
      + 'on an address already reported twice for exactly this kind of password guessing. Your own '
      + 'connection is home broadband in Ho Chi Minh City with a four millisecond response. This '
      + 'one took two hundred and twelve.',
      'It never got past the first step. Five wrong passwords, then it stopped, and it never saw '
      + 'your authenticator code or your key. Nothing of yours was read or changed.',
    ],
    predictions: [
      'Whoever ran this will most likely try again from a different address, because the cost of '
      + 'doing so is close to nothing.',
      'They know Morpheus is here and answering. Expect probing rather than a single burst.',
      'If any password you use elsewhere is also your Morpheus password, that is the real exposure.',
    ],
    recommended: [
      'Confirm your Morpheus password is used nowhere else. That is the one thing this attack relies on.',
      'Keep the authenticator code and hardware key switched on. They are why five guesses went nowhere.',
      'Block this address and network from the entry below, so a repeat never reaches the gate.',
    ],
  },
}

type Ctx = {
  locked: boolean
  unlock: () => void
  lock: () => void
  preview: PreviewMode
  setPreview: (m: PreviewMode) => void
  agents: Agent[]
  /** Runs Morph1 over one entry and attaches its report. Resolves when the reading is attached. */
  analyse: (id: string) => Promise<void>

  /* Agents */
  renameAgent: (id: string, name: string) => void
  deleteAgent: (id: string) => void
  setAgentActive: (id: string, active: boolean) => void

  /* OSINT objects */
  addObject: (name: string, kind: OsintObject['kind'], parentId?: string) => string
  renameObject: (id: string, name: string) => void
  deleteObject: (id: string) => void
  addInput: (objectId: string, item: Omit<InputItem, 'id' | 'updatedAt'>) => void
  removeInput: (objectId: string, inputId: string) => void
  /** Owner edit of one compiled field. Marks it as written rather than derived. */
  editField: (objectId: string, fieldId: string, value: string) => void
  /** Compiles the profile from the raw inputs. Resolves when it is attached. */
  buildProfile: (objectId: string) => Promise<void>
  factors: FactorSettings
  setFactors: (f: FactorSettings) => void
  tier: 'standard' | 'high' | 'paranoid'
  setTier: (t: 'standard' | 'high' | 'paranoid') => void
  access: AccessEntry[]
  ruleOn: (id: string, ruled: 'me' | 'not-me') => void
  blockSource: (id: string) => void
  /** Failed attempts since the owner was last here. Drives the arrival interrupt. */
  intrusions: AccessEntry[]
  models: ModelCard[]
  objects: OsintObject[]
}

const MorpheusSessionContext = createContext<Ctx | null>(null)

/**
 * Development bypass for the gate.
 *
 * There is no authentication here yet -- `unlock()` accepts any input -- so this skips a mock,
 * not a security boundary. It exists because reviewing the six pages behind the gate otherwise
 * means walking the whole unlock sequence on every reload.
 *
 * Guarded by `import.meta.env.DEV`, which Vite replaces with a literal `false` in a production
 * build, so the branch is dead code that the bundler removes entirely. When real authentication
 * lands, this function is deleted rather than adjusted -- an auth bypass that survives into a
 * shipped build is exactly the defect the gate is supposed to prevent.
 */
export function devBypassRequested(): boolean {
  if (!import.meta.env.DEV) return false
  try {
    return new URLSearchParams(window.location.search).has('open')
  } catch {
    return false
  }
}

// ── Fixtures ────────────────────────────────────────────────────────────────
// Marked sample data. Replaced by real records when the backend lands.
const SAMPLE_ACCESS: AccessEntry[] = [
  {
    id: 'a1', at: 'Today, 03:14:02', ok: true, verdict: 'you', confidence: 99, attempts: 1,
    summary: 'This machine, home wi-fi, first try',
    groups: [
      { group: 'Device', kind: 'device', signals: [
        { label: 'Machine name', value: 'DESKTOP-VLB', verdict: 'match' },
        { label: 'Account', value: 'vubinh', verdict: 'match' },
        { label: 'Operating system', value: 'Windows 11 (26200)', verdict: 'match' },
        { label: 'Browser', value: 'Chrome 141', verdict: 'match' },
        { label: 'Screen', value: '2560 x 1440', verdict: 'match' },
        { label: 'Timezone', value: 'Asia/Ho_Chi_Minh (UTC+7)', verdict: 'match' },
        { label: 'Language', value: 'en-GB, vi-VN', verdict: 'match' },
        { label: 'Device fingerprint', value: 'f4a1-9c72 (seen 412 times)', verdict: 'match' },
      ] },
      { group: 'Network', kind: 'network', signals: [
        { label: 'IP address', value: '113.161.44.87', verdict: 'match' },
        { label: 'Address type', value: 'Residential broadband', verdict: 'match' },
        { label: 'Provider', value: 'VNPT, AS45899', verdict: 'match' },
        { label: 'Reverse DNS', value: 'static.vnpt-hcm.vn', verdict: 'neutral' },
        { label: 'Location', value: 'Ho Chi Minh City, Vietnam', verdict: 'match' },
        { label: 'VPN or proxy', value: 'None detected', verdict: 'match' },
        { label: 'Round-trip latency', value: '4 ms (consistent with local)', verdict: 'match' },
        { label: 'Abuse listings', value: 'None', verdict: 'match' },
      ] },
      { group: 'Behaviour', kind: 'behaviour', signals: [
        { label: 'Typing rhythm match', value: '96%', verdict: 'match' },
        { label: 'Keystroke dwell time', value: '82 ms average', verdict: 'match' },
        { label: 'Time to first keystroke', value: '1.9 s', verdict: 'match' },
        { label: 'Corrections', value: 'None', verdict: 'match' },
        { label: 'Pasted into the field', value: 'No', verdict: 'match' },
        { label: 'Pointer movement', value: 'Present, human-shaped', verdict: 'match' },
      ] },
      { group: 'Attempt sequence', kind: 'sequence', signals: [
        { label: 'Attempts', value: '1' },
        { label: 'Reached second factor', value: 'Yes, passed' },
        { label: 'Factors used', value: 'Password, app code, hardware key' },
        { label: 'Hardware key serial', value: 'YK-5C-8831 (your key)', verdict: 'match' },
        { label: 'Total time at the gate', value: '11 s' },
      ] },
      { group: 'Context', kind: 'context', signals: [
        { label: 'Time of day', value: '03:14, within your usual hours', verdict: 'match' },
        { label: 'Entry point', value: 'Desktop shortcut' },
        { label: 'Other active sessions', value: 'None' },
        { label: 'Preceded by', value: 'TOBI session on the same machine', verdict: 'match' },
      ] },
    ],
  },
  {
    id: 'a2', at: 'Yesterday, 23:41:17', ok: true, verdict: 'likely', confidence: 94, attempts: 2,
    summary: 'This machine, one mistype, then in',
    groups: [
      { group: 'Device', kind: 'device', signals: [
        { label: 'Machine name', value: 'DESKTOP-VLB', verdict: 'match' },
        { label: 'Account', value: 'vubinh', verdict: 'match' },
        { label: 'Operating system', value: 'Windows 11 (26200)', verdict: 'match' },
        { label: 'Browser', value: 'Chrome 141', verdict: 'match' },
        { label: 'Device fingerprint', value: 'f4a1-9c72 (seen 411 times)', verdict: 'match' },
      ] },
      { group: 'Network', kind: 'network', signals: [
        { label: 'IP address', value: '113.161.44.87', verdict: 'match' },
        { label: 'Address type', value: 'Residential broadband', verdict: 'match' },
        { label: 'Location', value: 'Ho Chi Minh City, Vietnam', verdict: 'match' },
        { label: 'VPN or proxy', value: 'None detected', verdict: 'match' },
      ] },
      { group: 'Behaviour', kind: 'behaviour', signals: [
        { label: 'Typing rhythm match', value: '88%', verdict: 'match',
          note: 'Slower than usual, consistent with being tired rather than a different person.' },
        { label: 'Keystroke dwell time', value: '104 ms average', verdict: 'neutral' },
        { label: 'Time to first keystroke', value: '2.4 s' },
        { label: 'Corrections', value: '1 backspace', verdict: 'neutral' },
        { label: 'Pasted into the field', value: 'No', verdict: 'match' },
        { label: 'Pointer movement', value: 'Present, human-shaped', verdict: 'match' },
      ] },
      { group: 'Attempt sequence', kind: 'sequence', signals: [
        { label: 'Attempts', value: '2' },
        { label: 'First failure reason', value: 'Password mistyped, 1 character short' },
        { label: 'Gap between attempts', value: '3.8 s', verdict: 'match',
          note: 'A human pause. Scripted retries are near-instant and evenly spaced.' },
        { label: 'Reached second factor', value: 'Yes, passed' },
        { label: 'Factors used', value: 'Password, app code' },
        { label: 'Hardware key serial', value: null, note: 'The key was not plugged in for this session.' },
      ] },
      { group: 'Context', kind: 'context', signals: [
        { label: 'Time of day', value: '23:41, late but within your range', verdict: 'neutral' },
        { label: 'Entry point', value: 'TOBI sidebar' },
        { label: 'Other active sessions', value: 'None' },
      ] },
    ],
  },
  {
    id: 'a3', at: 'Aug 14, 02:07:55', ok: false, verdict: 'unknown', confidence: 8, attempts: 5,
    summary: 'Unknown machine, five failures, never opened',
    groups: [
      { group: 'Device', kind: 'device', signals: [
        { label: 'Machine name', value: null, note: 'Not reported. Your own machine always reports one.' },
        { label: 'Account', value: null },
        { label: 'Operating system', value: 'Linux x86_64', verdict: 'mismatch' },
        { label: 'Browser', value: 'Chrome 119, automation flags present', verdict: 'mismatch',
          note: 'The browser identified itself as being driven by software, not a person.' },
        { label: 'Screen', value: '1280 x 720', verdict: 'mismatch',
          note: 'A default virtual-machine resolution, not a real monitor.' },
        { label: 'Timezone', value: 'UTC+0', verdict: 'mismatch' },
        { label: 'Language', value: 'en-US only', verdict: 'mismatch' },
        { label: 'Device fingerprint', value: '0b3e-77af (never seen before)', verdict: 'mismatch' },
      ] },
      { group: 'Network', kind: 'network', signals: [
        { label: 'IP address', value: '45.83.punctured.19 (partially masked)', verdict: 'mismatch' },
        { label: 'Address type', value: 'Datacenter', verdict: 'mismatch',
          note: 'Rented server space. Ordinary people do not browse from datacenters.' },
        { label: 'Provider', value: 'M247 Europe, AS9009', verdict: 'mismatch' },
        { label: 'Reverse DNS', value: null },
        { label: 'Location', value: 'Amsterdam, Netherlands (per address registry)', verdict: 'mismatch' },
        { label: 'VPN or proxy', value: 'Commercial VPN exit node', verdict: 'mismatch' },
        { label: 'Round-trip latency', value: '212 ms', verdict: 'mismatch',
          note: 'Far higher than your own connection, and consistent with a relay.' },
        { label: 'Abuse listings', value: 'Listed on 2 credential-stuffing feeds', verdict: 'mismatch' },
      ] },
      { group: 'Behaviour', kind: 'behaviour', signals: [
        { label: 'Typing rhythm match', value: '12%', verdict: 'mismatch' },
        { label: 'Keystroke dwell time', value: '0 ms', verdict: 'mismatch',
          note: 'No key was physically held down. The text arrived all at once.' },
        { label: 'Time to first keystroke', value: '0.1 s', verdict: 'mismatch' },
        { label: 'Corrections', value: 'None across five attempts', verdict: 'mismatch',
          note: 'Nobody types five different passwords without a single correction.' },
        { label: 'Pasted into the field', value: 'Yes, on all five attempts', verdict: 'mismatch',
          note: 'Consistent with working through a list of stolen passwords.' },
        { label: 'Pointer movement', value: 'None recorded', verdict: 'mismatch',
          note: 'The strongest single signal here. A person moves the mouse; a script never does.' },
      ] },
      { group: 'Attempt sequence', kind: 'sequence', signals: [
        { label: 'Attempts', value: '5, all failed' },
        { label: 'Attempt times', value: '02:07:55, :57, :58, :59, 02:08:01' },
        { label: 'Gap between attempts', value: '1.2 s, near-identical each time', verdict: 'mismatch',
          note: 'Machine-even spacing. Human retries vary.' },
        { label: 'Password lengths tried', value: '8, 8, 12, 10, 14 characters',
          note: 'Lengths only. Morpheus never stores what was typed.' },
        { label: 'Reached second factor', value: 'No, stopped at the password' },
        { label: 'Hardware key serial', value: null, note: 'No key was ever presented.' },
        { label: 'Total time at the gate', value: '6 s' },
      ] },
      { group: 'Context', kind: 'context', signals: [
        { label: 'Time of day', value: '02:07, outside your active hours', verdict: 'mismatch' },
        { label: 'Entry point', value: 'Direct address, no referrer', verdict: 'mismatch',
          note: 'They knew the address. It was not reached from TOBI.' },
        { label: 'Other active sessions', value: 'None. You were not online.' },
        { label: 'Preceded by', value: 'No TOBI session', verdict: 'mismatch' },
        { label: 'Similar attempts elsewhere', value: null,
          note: 'Morpheus has no visibility outside this machine, so it cannot say.' },
      ] },
    ],
  },
]

const SAMPLE_AGENTS: Agent[] = [
  {
    id: 'morph1', name: 'Morph1', role: 'Security analyst',
    active: true, status: 'ready', runs: 3, lastRun: 'Aug 14, 02:09',
    model: 'Ministral 3 14B', created: 'Aug 12, 2026',
    description: 'Reads an attempt on the gate and tells you, in plain words, what happened and what it means.',
    detail:
      'Morph1 takes the full forensic capture of a single access attempt and turns it into a '
      + 'judgement you can act on. It separates a person at a keyboard from an automated script, '
      + 'weighs the network against your usual one, compares typing behaviour to your baseline, '
      + 'and states what the attacker was probably trying to achieve. It also predicts what is '
      + 'likely to follow, which is usually the part that decides whether you need to do anything '
      + 'tonight or on Monday.',
    skills: [
      'Reads an access attempt and explains it in plain language',
      'Separates a person from an automated script',
      'Judges whether a network address is residential, hosted or relayed',
      'Compares behaviour against your established baseline',
      'Names what the attacker was probably trying to achieve',
      'Predicts what is likely to happen next',
    ],
    limits: [
      'Reads only. It cannot block, lock, or change a setting on its own.',
      'Sees only what Morpheus captured on this machine.',
      'Never sees the characters of a password, only how many there were.',
    ],
  },
  {
    id: 'sable', name: 'Sable', role: 'OSINT compiler',
    active: true, status: 'idle', runs: 11, lastRun: 'Yesterday, 23:10',
    model: 'Qwen 27B (abliterated)', created: 'Aug 09, 2026',
    description: 'Turns the raw material on an object into a profile where every line names its source.',
    detail:
      'Sable reads everything held under an object -- files, addresses, handles, notes -- and '
      + 'compiles it into a single picture. Its one rule is that nothing may appear in the profile '
      + 'without pointing back at the raw item it came from, so any claim can be checked in one '
      + 'click. Where the material contradicts itself it says so rather than picking a winner.',
    skills: [
      'Groups scattered material into a readable profile',
      'Attaches evidence to every field it writes',
      'Flags contradictions instead of resolving them silently',
      'Re-runs against new material and shows what changed',
    ],
    limits: [
      'Reads only what you have already collected. It does not go and search.',
      'Never merges two objects on its own judgement.',
    ],
  },
  {
    id: 'wren', name: 'Wren', role: 'Watcher',
    active: false, status: 'idle', runs: 0, lastRun: null,
    model: 'Ministral 3 14B', created: 'Aug 18, 2026',
    description: 'Re-runs an object on a schedule and tells you only what changed.',
    detail:
      'Wren keeps an object under observation and compares each run against the last, reporting '
      + 'differences rather than restating the whole picture. It is deactivated until you decide '
      + 'what it is allowed to watch and how often, because a watcher nobody configured is just '
      + 'background noise with a schedule.',
    skills: [
      'Re-runs a profile and diffs it against the previous one',
      'Reports only the difference, never the whole profile again',
      'Escalates when a change crosses a threshold you set',
    ],
    limits: [
      'Deactivated until you give it a target and a cadence.',
      'Cannot act on what it finds. It reports and stops.',
    ],
  },
]

const SAMPLE_MODELS: ModelCard[] = [
  {
    id: 'ministral-3-14b', name: 'Ministral 3 14B', where: 'local', admitted: true, active: true,
    power: 62, freedom: 94, source: 'SpeechMap Free Speech Index', sourceUrl: 'https://speechmap.ai/',
    license: 'Apache-2.0', hardware: '12 to 16 GB GPU',
    note: 'Lowest refusal rate of any lab, with no modification needed.',
  },
  {
    id: 'qwen-27b-abl', name: 'Qwen 27B (abliterated)', where: 'local', admitted: true,
    power: 74, freedom: 98, source: 'Refusal-direction study, arXiv 2512.13655',
    sourceUrl: 'https://arxiv.org/html/2512.13655v1', license: 'Apache-2.0', hardware: '24 GB GPU',
    note: 'Refusal behaviour removed from the weights. Costs some maths reasoning.',
  },
  {
    id: 'llama-70b-abl', name: 'Llama 3.3 70B (abliterated)', where: 'local', admitted: false,
    power: 88, freedom: 90, source: 'Refusal-direction study, arXiv 2512.13655',
    sourceUrl: 'https://arxiv.org/html/2512.13655v1', license: 'Llama 3.3 Community',
    hardware: 'Two 24 GB GPUs', note: 'Strongest of the local options, and the heaviest to run.',
  },
  {
    id: 'claude-opus', name: 'Claude Opus', where: 'hosted', admitted: false,
    power: 97, freedom: 40, source: 'SpeechMap sensitive-prompt set', sourceUrl: 'https://speechmap.ai/',
    license: 'Provider terms', hardware: 'Provider servers',
    note: 'Guardrails live in the weights on the provider’s machines. They cannot be removed.',
  },
  {
    id: 'gpt-5x', name: 'GPT-5.x', where: 'hosted', admitted: false,
    power: 95, freedom: 38, source: 'SpeechMap sensitive-prompt set', sourceUrl: 'https://speechmap.ai/',
    license: 'Provider terms', hardware: 'Provider servers',
    note: 'Bypassing provider safeguards is prohibited by their usage policy.',
  },
]

const SAMPLE_OBJECTS: OsintObject[] = [
  {
    id: 'acme-robotics.com', name: 'acme-robotics.com', kind: 'Domain', built: '2 hours ago',
    sources: 14, confidence: 82, flagged: true,
    summary: 'Warehouse automation firm, Austin. A Cyprus subsidiary appeared shortly before a US contract award.',
    inputs: [
      { id: 'i1', kind: 'link', label: 'Website', value: 'https://acme-robotics.com', origin: 'You, pasted', updatedAt: '2 hours ago' },
      { id: 'i2', kind: 'email', label: 'Pattern', value: 'first.last@acme-robotics.com', origin: 'MX and staff pages', updatedAt: '2 hours ago' },
      { id: 'i3', kind: 'location', label: 'Registered office', value: 'Austin, Texas', origin: 'WHOIS', updatedAt: '2 hours ago' },
      { id: 'i4', kind: 'note', label: 'Cyprus entity', value: 'Acme Robotics EU registered 4 months before a US contract award', origin: 'registry.cy filing', updatedAt: '2 hours ago' },
    ],
    profile: [],
  },
  {
    id: 'elena-vasquez', name: 'Elena Vasquez', kind: 'Person', built: 'Yesterday',
    sources: 18, confidence: 74, flagged: false, parentId: 'acme-robotics.com',
    summary: 'Co-founder and CTO at Acme Robotics. Ex-Boston Dynamics. Active on two networks.',
    inputs: [
      { id: 'p1', kind: 'name', label: 'Full name', value: 'Elena Marie Vasquez', origin: 'Company filing', updatedAt: 'Yesterday' },
      { id: 'p2', kind: 'email', label: 'Work email', value: 'elena.vasquez@acme-robotics.com', origin: 'Conference programme', updatedAt: 'Yesterday' },
      { id: 'p3', kind: 'phone', label: 'Office line', value: '+1 512 555 0148', origin: 'Company contact page', updatedAt: '3 days ago' },
      { id: 'p4', kind: 'social', label: 'LinkedIn', value: 'in/elena-vasquez-robotics', origin: 'Public search', updatedAt: 'Yesterday' },
      { id: 'p5', kind: 'social', label: 'Instagram', value: '@elena.builds', origin: 'Cross-referenced username', updatedAt: '4 days ago' },
      { id: 'p6', kind: 'location', label: 'Based', value: 'Austin, Texas', origin: 'Conference bio', updatedAt: 'Yesterday' },
      { id: 'p7', kind: 'image', label: 'Press photo', value: 'acme-press-2026.jpg', origin: 'Series B announcement', updatedAt: '2 days ago' },
      { id: 'p8', kind: 'note', label: 'Prior role', value: 'Robotics engineer at Boston Dynamics, 2016 to 2019', origin: 'Two press pieces', updatedAt: 'Yesterday' },
    ],
    profile: [
      { id: 'sec-id', title: 'Identity', fields: [
        { id: 'f1', label: 'Full name', value: 'Elena Marie Vasquez', from: ['p1'] },
        { id: 'f2', label: 'Based in', value: 'Austin, Texas', from: ['p6', 'p3'] },
      ] },
      { id: 'sec-role', title: 'Position', fields: [
        { id: 'f3', label: 'Current', value: 'Co-founder and CTO, Acme Robotics', from: ['p2', 'p4'] },
        { id: 'f4', label: 'Previous', value: 'Robotics engineer, Boston Dynamics (2016 to 2019)', from: ['p8'] },
      ] },
      { id: 'sec-contact', title: 'Contact', fields: [
        { id: 'f5', label: 'Email', value: 'elena.vasquez@acme-robotics.com', from: ['p2'] },
        { id: 'f6', label: 'Phone', value: '+1 512 555 0148', from: ['p3'] },
      ] },
      { id: 'sec-online', title: 'Online presence', fields: [
        { id: 'f7', label: 'LinkedIn', value: 'in/elena-vasquez-robotics', from: ['p4'] },
        { id: 'f8', label: 'Instagram', value: '@elena.builds', from: ['p5'] },
      ] },
    ],
    profileBuiltAt: 'Yesterday, 23:10',
  },
  {
    id: 'northwind-capital', name: 'Northwind Capital', kind: 'Company', built: 'Yesterday',
    sources: 21, confidence: 76, flagged: false,
    summary: 'Investment vehicle with three named partners and a thin public footprint.',
    inputs: [
      { id: 'n1', kind: 'link', label: 'Website', value: 'https://northwind-capital.example', origin: 'You, pasted', updatedAt: 'Yesterday' },
      { id: 'n2', kind: 'note', label: 'Partners', value: 'Three named partners on the filing', origin: 'Companies register', updatedAt: 'Yesterday' },
    ],
    profile: [],
  },
  {
    id: '203.0.113.44', name: '203.0.113.44', kind: 'IP', built: '3 days ago',
    sources: 9, confidence: 91, flagged: false,
    summary: 'Hosting endpoint tied to two of the domains already in your library.',
    inputs: [
      { id: 'ip1', kind: 'note', label: 'Reverse DNS', value: 'edge-04.hosting.example', origin: 'DNS lookup', updatedAt: '3 days ago' },
    ],
    profile: [],
  },
]

export function MorpheusSessionProvider({ children }: { children: ReactNode }) {
  const [locked, setLocked] = useState(() => !devBypassRequested())
  const [factors, setFactors] = useState<FactorSettings>({ code: true, key: true })
  const [tier, setTier] = useState<'standard' | 'high' | 'paranoid'>('high')
  const [access, setAccess] = useState<AccessEntry[]>(SAMPLE_ACCESS)
  const [preview, setPreview] = useState<PreviewMode>('live')
  const [objects, setObjects] = useState<OsintObject[]>(SAMPLE_OBJECTS)
  const [agents, setAgents] = useState<Agent[]>(SAMPLE_AGENTS)

  const renameAgent = useCallback((id: string, name: string) => {
    setAgents(p => p.map(a => (a.id === id ? { ...a, name } : a)))
  }, [])
  const deleteAgent = useCallback((id: string) => {
    setAgents(p => p.filter(a => a.id !== id))
  }, [])
  const setAgentActive = useCallback((id: string, active: boolean) => {
    setAgents(p => p.map(a => (a.id === id ? { ...a, active, status: active ? 'ready' : 'idle' } : a)))
  }, [])

  const patchObject = useCallback((id: string, fn: (o: OsintObject) => OsintObject) => {
    setObjects(p => p.map(o => (o.id === id ? fn(o) : o)))
  }, [])

  const addObject = useCallback((name: string, kind: OsintObject['kind'], parentId?: string) => {
    const id = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || `object-${Date.now()}`
    setObjects(p => (p.some(o => o.id === id) ? p : [{
      id, name: name.trim(), kind, parentId, built: 'Just now', sources: 0, confidence: 0,
      flagged: false, summary: 'No data gathered yet.', inputs: [], profile: [],
    }, ...p]))
    return id
  }, [])

  const renameObject = useCallback((id: string, name: string) => {
    patchObject(id, o => ({ ...o, name }))
  }, [patchObject])

  const deleteObject = useCallback((id: string) => {
    setObjects(p => p.filter(o => o.id !== id && o.parentId !== id))
  }, [])

  const addInput = useCallback((objectId: string, item: Omit<InputItem, 'id' | 'updatedAt'>) => {
    patchObject(objectId, o => ({
      ...o,
      inputs: [...o.inputs, { ...item, id: `in${Date.now()}`, updatedAt: 'Just now' }],
    }))
  }, [patchObject])

  const removeInput = useCallback((objectId: string, inputId: string) => {
    patchObject(objectId, o => ({ ...o, inputs: o.inputs.filter(i => i.id !== inputId) }))
  }, [patchObject])

  const editField = useCallback((objectId: string, fieldId: string, value: string) => {
    patchObject(objectId, o => ({
      ...o,
      profile: o.profile.map(s => ({
        ...s,
        fields: s.fields.map(f => (f.id === fieldId ? { ...f, value, manual: true } : f)),
      })),
    }))
  }, [patchObject])

  /**
   * Compile the raw inputs into a profile.
   *
   * SHELL ONLY: the grouping below stands in for the agent. What matters for review is the
   * SHAPE -- every field carries the ids of the inputs it came from, so nothing in the finished
   * profile can exist without something in the raw data to point at.
   */
  const buildProfile = useCallback(async (objectId: string) => {
    await new Promise(r => setTimeout(r, 1600))
    setObjects(prev => prev.map(o => {
      if (o.id !== objectId) return o
      const pick = (...kinds: InputKind[]) => o.inputs.filter(i => kinds.includes(i.kind))
      const section = (id: string, title: string, items: InputItem[]): ProfileSection => ({
        id, title,
        fields: items.map(i => ({ id: `f-${i.id}`, label: i.label, value: i.value, from: [i.id] })),
      })
      const built = [
        section('sec-id', 'Identity', pick('name', 'location')),
        section('sec-contact', 'Contact', pick('email', 'phone')),
        section('sec-online', 'Online presence', pick('social', 'link')),
        section('sec-notes', 'Notes and material', pick('note', 'file', 'image')),
      ].filter(s => s.fields.length > 0)
      return { ...o, profile: built, profileBuiltAt: 'Just now' }
    }))
  }, [])

  const unlock = useCallback(() => setLocked(false), [])
  const lock = useCallback(() => setLocked(true), [])

  const ruleOn = useCallback((id: string, ruled: 'me' | 'not-me') => {
    setAccess(p => p.map(e => (e.id === id ? { ...e, ruled } : e)))
  }, [])

  const blockSource = useCallback((id: string) => {
    setAccess(p => p.map(e => (e.id === id ? { ...e, blocked: true, ruled: 'not-me' } : e)))
  }, [])

  // SHELL ONLY: the delay stands in for the agent actually reading the entry, so the working
  // state on the button is real rather than decorative.
  const analyse = useCallback(async (id: string) => {
    await new Promise(r => setTimeout(r, 1400))
    setAccess(p => p.map(e => (e.id === id ? { ...e, report: REPORTS[e.id] } : e)))
  }, [])

  const intrusions = useMemo(() => access.filter(e => !e.ok && e.ruled !== 'me'), [access])

  const value = useMemo<Ctx>(() => ({
    locked, unlock, lock, preview, setPreview, factors, setFactors, tier, setTier,
    access: preview === 'empty' ? [] : access, ruleOn, blockSource, intrusions, analyse,
    agents: preview === 'empty' ? [] : agents,
    models: preview === 'empty' ? [] : SAMPLE_MODELS,
    objects: preview === 'empty' ? [] : objects,
    renameAgent, deleteAgent, setAgentActive,
    addObject, renameObject, deleteObject, addInput, removeInput, editField, buildProfile,
  }), [locked, unlock, lock, preview, factors, tier, access, ruleOn, blockSource, intrusions,
    analyse, objects, agents, renameAgent, deleteAgent, setAgentActive,
    addObject, renameObject, deleteObject, addInput, removeInput, editField, buildProfile])

  return <MorpheusSessionContext.Provider value={value}>{children}</MorpheusSessionContext.Provider>
}

export function useMorpheus() {
  const ctx = useContext(MorpheusSessionContext)
  if (!ctx) throw new Error('useMorpheus must be used within MorpheusSessionProvider')
  return ctx
}
