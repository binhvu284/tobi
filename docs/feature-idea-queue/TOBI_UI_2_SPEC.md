# TOBI Agent Mission Control UI 2.0

> **Queue status:** 🟡 Queued · **Depends on:** [Mission Control Infrastructure V2](MISSION_CONTROL_INFRASTRUCTURE_V2_PLAN.md) (the one engine behind every request) and [TOBI Conductor](CONDUCTOR_SPEC.md) (plain words to MC work) · **Owner-reviewed:** UI shell accepted 2026-08-30; 30 backend answers captured below
> Part of the [Feature Development Queue](QUEUE.md). Item **#36**.

## The idea, in the owner's words

Mission Control today is rich and full-featured, but it still asks for a lot of clicking. UI 2.0 exists to collapse that: talk or type to TOBI in real time, he answers, uses tools, and does the work — all on one screen, so the owner never has to leave it and still reaches every feature. Including the ones that are themselves Mission Control settings: *"I can even ask TOBI to change the theme of MC by talking to him."*

## What is already done

**The UI shell is finished and accepted.** It is a working prototype, not a mockup: every state, effect, and component in it is real and was verified headlessly before sign-off.

- **File:** [`TOBI_UI_2_SHELL.html`](TOBI_UI_2_SHELL.html) — open it in a browser, no build step.
- **Build the front end to match it exactly.** Components, motion, timing, tokens, copy, and behaviour are decided. No part of it is a placeholder to be reinterpreted.

### What the shell already fixes

| Area | Decided |
|---|---|
| Screens | **01 Starting screen** (asleep → a real staged boot → hands over) and **02 Canvas view** (the session running) |
| Console layout | A fixed neuron head, one scrolling exchange, a dock that never moves. **One exchange on screen at a time**; the Script panel keeps every one. |
| Agent states | Five, from one table: `idle · listening · thinking · working · speaking`. The graph, the status line, and the transcript are three views of one state and cannot disagree. |
| Graph behaviour | Still at rest. The wave runs **outward** while he answers and **inward** while he listens. Amplitude and rate ease; the phase carries over so a rate change never jumps the wave. The tick wheel always turns; the middle ring lights only while he works. |
| Status line | Never generic: action word plus the specific thing (`Reading the brain for Monolith 1`), shimmering while under way, with **elapsed time and tokens for the run**. Hidden at rest, giving its height back. |
| Tool calls | An action row per step: appears when the step starts, spins while it runs, is replaced by its own result. **Three or more fold** into one summary. |
| Failure | A failed step names what failed, **whose fault it was** (service vs TOBI), what it costs, and offers **Try again**. The run continues; the answer owns up to it. |
| Control | `Esc to stop`. Stopping keeps every step that landed and says how far it got. |
| Voice modes | **On and off** (`Alt M`), **Push to talk** (hold `Space`), **Locked** (menu only, where every session starts). `Esc` returns to Locked. A live partial transcript appears as he hears it. |
| Canvas | Four panels (Artifacts · Script · History · Configure) open **single, no tab bar**, one at a time. Anything picked from a panel becomes a **document**, and documents are what the tab bar is for; four stay open, a fifth parks the oldest. |
| Canvas width | Follows its content: **30%** for a list or settings, **50%** for anything read. Not a setting. The edge drags freely and sticks to 30 / 50 / 70. |
| Typing | Queues behind him, never interrupts. |
| Design system | Theme v2 tokens verbatim, plus scales for type (7), space (5), radius (4 + pill), duration (3), and depth (5 named layers). Every colour is a token. |
| Accessibility | Every animation inside a `prefers-reduced-motion` guard; the status line is a polite live region; a `@supports` fallback keeps shimmering labels readable where `background-clip: text` is unsupported. |

### Two additions the Q&A produced

The shell needs these before the build starts. Both are small.

1. **A speaker control** — an on/off toggle and a **volume slider** for TOBI's voice, so the owner sets how loud he is and can mute him without leaving the screen (Q7).
2. **The rail label** — the page is called **UI 2.0**, first item in the Main group, above Dashboard (Q26).

### Build status: P1 front end delivered (2026-09-06)

The shell is now a real page at `/ui2`, first in the rail's Main group, built to the shell's own CSS (generated from it by `scripts/ui2_css.mjs`, not retyped). Both additions above are in. What the page does today:

- Both screens, the five states, the status line with elapsed time and tokens, action rows that fold at three, failure with whose fault and Try again, `Esc` to stop with the kept steps counted, the three voice modes as controls, the speaker on/off and volume, the four canvas panels, document tabs that park the fifth, canvas width by content with the magnetic grip, typing that queues.
- **Typed turns are wired to the Chat runtime** in agent mode, which is where Conductor's tools run: steps become action rows, usage becomes the receipt and the context donut, a risky action becomes a one-line confirmation that calls Conductor's confirm endpoint, and artifacts open on the canvas.
- The boot runs five real checks (model, projects, tools, canvas, voice) on the shell's clock and fails truthfully with the reason and Try again.
- `?demo=1` runs the shell's scripted session, so the build can be checked against the design one state at a time. Verified headlessly in Edge, every state, zero runtime errors.

Not yet: everything voice (P2), backend session persistence and reload, the budget cap, real MC pages inside the canvas (P3), and the acceptance case (P4). History is kept in the browser until P3. See [`../MISSION_CONTROL.md`](../MISSION_CONTROL.md#ui-20-live-screen-36-phase-1) for the file map.

## Decisions (from 30 owner answers)

### Voice in

| # | Area | Decision |
|---|---|---|
| 1 | Speech-to-text | **Several providers behind one adapter**, switchable from Configure mid-session |
| 2 | Default | **Deepgram Nova** — 92ms to first word, best measured accuracy, ~$0.008/min |
| 3 | How listening starts | **The three modes already in the shell.** No wake word, no always-on microphone |
| 4 | Language | **English only** |

### Voice out

| # | Area | Decision |
|---|---|---|
| 5 | Text-to-speech | **Several providers behind one adapter**, same shape as speech-to-text |
| 6 | Default voice | **ElevenLabs** — the best-sounding option; switch to a cheaper one for long output |
| 7 | Owner control | **An on/off toggle and a volume slider.** Not a policy about when he speaks — a control the owner holds |
| 8 | Interrupting | **Barge-in: he stops mid-word** the moment the owner speaks |

### Architecture

| # | Area | Decision |
|---|---|---|
| 9 | Shape | **A pipeline the owner controls** — speech in, MC's own model, speech out, each part swappable. Costs 200–400ms over single-model speech-to-speech, and is the only shape that keeps MC's model routing and Brain context |
| 10 | Transport | **WebSocket** — one connection carrying audio, transcripts, state, and tool events |
| 11 | Turn detection | **Semantic endpointing** — a model predicts the sentence is finished rather than counting silence. Research puts this at 200–600ms faster with ~30% fewer wrong interruptions |
| 12 | Where audio is processed | **The browser talks to providers directly.** Backend mints **short-lived tokens** so real keys never reach the front end *(refinement offered by Claude, owner to confirm)* |

### What TOBI can do

| # | Area | Decision |
|---|---|---|
| 13 | Capability source | **Build on Conductor and the V2 engine.** UI 2.0 is a new front end onto those, not a second brain. Every capability Conductor gains, this gains |
| 14 | v1 scope | **Whatever Conductor already does.** They grow together |
| 15 | Changing MC by voice | **Yes, and the canvas shows what changed**, with an undo |
| 16 | Confirmation | **Anything that leaves the machine or cannot be undone.** Reading, searching, opening happen instantly; sending, deleting, publishing, spending, or changing a credential asks first, in one line, naming the exact thing |

### Session and state

| # | Area | Decision |
|---|---|---|
| 17 | What a session is | **A conversation with a recap** — Start to End, saved to History with a summary he can be asked about later |
| 18 | Versus Chat | **Separate surfaces, shared memory.** Chat stays for long typed work; both read and write the same Brain |
| 19 | Reload | **It comes back where it was.** The session lives on the backend: same transcript, same canvas, same state |
| 20 | More than one place | **One live session at a time.** Opening it elsewhere says so and offers to move it |

### Cost, privacy, failure

| # | Area | Decision |
|---|---|---|
| 21 | Budget | **A visible running cost and a cap the owner sets.** It stops and asks at the limit. Reuses the per-call cost tracking from [Storage & Usage](STORAGE_USAGE_SPEC.md) |
| 22 | Audio | **Transcribed, then discarded.** Never written to disk. The transcript is kept |
| 23 | Provider outage | **Fall back silently, say so once** in the transcript |
| 24 | Unattended work | **Yes — long jobs carry on if the owner leaves**, and the recap says what happened. The V2 engine already survives crashes |

### Surface

| # | Area | Decision |
|---|---|---|
| 25 | Canvas content | **Real MC pages rendered inside it** — the actual Runs chart, not a copy. Each page must render without its own chrome |
| 26 | Where it lives | **A separate page named "UI 2.0"**, first in the Main group, above Dashboard. The Live Screen page is renamed to it |
| 27 | Memory | **Brain V2 decides**, through its existing curation. Voice does not get to pollute memory with filler |
| 28 | Mobile | **Desktop first, and do not block mobile.** The session lives on the backend, so a phone client is a front-end job later, not a rebuild |

### Delivery

| # | Area | Decision |
|---|---|---|
| 29 | Done means | **Both a proved run and a measured feel.** A frozen end-to-end case run for real *and* conversational latency inside the numbers below. Nothing ships on a claim |
| 30 | Build first | **The shell, wired to Conductor, typed only.** A usable screen in the first week, and every voice decision lands on something that already works |

## Acceptance gate

Two halves, both required, in the evidence-gated style of #34 and #35.

**Half one — a real session, proved.** One frozen case, run against a committed revision, recording every step:

1. The owner speaks a request.
2. TOBI transcribes it, uses at least one real tool, and puts a real MC view on the canvas.
3. He answers out loud.
4. The session ends and writes a recap to History.
5. The next day, asking about that session returns the recap.

**Half two — it feels like a conversation.** "Feels right" is not a gate, so it is stated as numbers taken from the research:

| Measure | Target | Why this number |
|---|---|---|
| First word heard → transcript | **< 150ms** | Deepgram measures 92ms; 150 leaves room for the hop |
| End of speech → he starts answering | **< 900ms** | Under a second is the threshold where a pause reads as thinking, not lag |
| Owner speaks → he stops talking | **< 200ms** | Slower than this and barge-in feels ignored |
| Wrong interruptions | **< 5%** of turns | Semantic endpointing should land well inside this |

## Build order

| Phase | What | Rough size |
|---|---|---|
| **P1** | The shell as real components, wired to Conductor, typed only. Add the speaker control and the rail rename. | 5–8 focus days |
| **P2** | The voice pipeline: adapters for speech-to-text and text-to-speech, semantic endpointing, barge-in, the WebSocket session. | 5–7 focus days |
| **P3** | Session persistence and reload, the budget meter and cap, the confirmation policy, real MC pages inside the canvas. | 4–6 focus days |
| **P4** | The frozen acceptance case and the latency measurements. | 2 focus days |

**Provisional size: `XXL`, 16–22 focus days, 4–6 calendar weeks.** The number that moves it most is P1, because the shell is deliberately detailed and matching it exactly is the point.

## Open

- **Q12 refinement:** ephemeral tokens for browser-to-provider calls, so real keys never sit in the front end. Same latency; a leaked token dies in minutes. Awaiting the owner's yes or no.
- **Canvas prerequisite:** Q25 requires MC pages to render without their own sidebar and header. How many already can is unknown and needs a survey before P3 is sized.

## Sources

Voice provider and turn-detection figures come from independent 2026 benchmarks: [Coval STT benchmarks](https://www.coval.ai/blog/best-speech-to-text-providers-in-2026-independent-benchmarks-and-how-to-choose/), [Deepgram voice-agent architecture](https://deepgram.com/learn/voice-agent-architecture-stt-llm-tts-pipeline-design), [LiveKit on turn detection](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection), [AssemblyAI on endpointing](https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent), [Kanopy: OpenAI Realtime vs LiveKit vs ElevenLabs](https://kanopylabs.com/blog/openai-realtime-api-vs-livekit-agents-vs-elevenlabs).
