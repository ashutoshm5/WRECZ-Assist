# WRECZ architecture

A local Windows assistant. Speech, intent classification and system control all
run on the machine; nothing is sent to a hosted service. This document covers
both repositories: the Python backend (`wrecz`) and the React/Tauri frontend
(`wrecz-frontend`).

For the wire protocol see `INTEGRATION.md`. For the desktop shell see
`../wrecz-frontend/DESKTOP.md`.

---

## 1. Processes

Three processes, all bound to localhost.

```
  wrecz.exe  (Tauri shell, Rust)
      |  owns the window, and spawns/kills the bridge
      |
      +-- WebView2 ---------> Vite dev server  127.0.0.1:8443
      |                       React app, waveform, conversation box
      |                          |
      |                          |  ws://127.0.0.1:8765/ws   conversation, confirmations, audio
      |                          |  http://127.0.0.1:8765/api status, settings
      |                          v
      +-- python -m uvicorn api_server:app   127.0.0.1:8765
              |
              +-- core.brain ---- http --> Ollama 127.0.0.1:11434  (wrecz-brain)
              +-- core.router --> skills/  (apps, files, volume, brightness, wifi, bluetooth, web)
              +-- security.gate  SecurityCore + tray + activity log
              +-- voice          Kokoro -> sounddevice -> speakers
```

Ollama is a separate service WRECZ does not manage. If it is down, the
deterministic half of intent routing still works (see §3); anything needing the
model fails with a clear error.

The browser path (`python run_all.py`, then open `127.0.0.1:8443`) uses the same
bridge. The Tauri shell only replaces the window and the process supervision.

`main.py` is the original CLI and still runs standalone. It is deliberately
untouched by the bridge work: every change made for the frontend defaults to
the CLI's previous behaviour.

---

## 2. Request lifecycle

One user message, end to end:

```
1  frontend      send {type:"message", text}                    useWrecz.send
2  bridge        queue it; receive loop stays free              api_server:/ws
3  bridge        {type:"state", busy:true}
4  worker thread runtime.process(text, channel)                 holds request_lock
5  brain         rules, then the model if no rule matched       core.brain.ask_wrecz
6  router        execute the command                            core.router.Router
     |
     +- needs internet?  -> security.gate.check_internet
     +- needs confirming? -> core.prompt.ask_confirmation ---> {type:"confirm"}
                                     (worker parks here)   <--- {type:"confirm", allowed}
7  bridge        {type:"response", text, intent, action}
8  bridge        {type:"status", ...}                           internet may have changed
9  voice         Kokoro speaks the result, in 512-sample slices
     |             each slice -> {type:"voice", event:"samples"} -> waveform
10 bridge        {type:"state", busy:false}
```

The important property is step 2. The WebSocket receive loop never blocks on the
request it is serving, which is the only reason step 6's confirmation round trip
can work at all.

---

## 3. Intent routing

Two tiers, in order. This is the core design decision in the backend.

**Tier 1 — deterministic rules** (`core/brain.py`: `_local_intent`,
`_web_search_intent`, `_application_intent`). Regex over the cleaned text.
Instant (~0.2 ms) and unaffected by Ollama being down. Owns:

- Wi-Fi, Bluetooth, volume, brightness — including relative forms
  ("make it quieter", "dim the screen")
- web search in all its common phrasings
- application open/close

**Tier 2 — the model** (`_classify_with_llm`). A `wrecz-brain` (phi4-mini)
call constrained by a JSON schema, given a few turns of context. ~3.4 s warm.
Handles open-ended phrasing and normal conversation.

Measured on the same 14 commands: rules 14/14 at 0.16 ms; model 13/14 at 3.4 s.
They fail on *different* inputs, which is why both exist.

The rules are deliberately **narrow**. A rule only claims a request when the
phrase is confidently a command; anything with a joining word, an indefinite
article, or more than four words is handed to the model rather than forced into
a wrong action. `"open chrome"` is a rule; `"start a conversation"` is not.

`core/conversation.py` holds a short rolling memory so "close it", "a bit more"
and "again" resolve against the previous turn before classification.

The classifier prompt is load-bearing. It previously contained the line
"You do NOT access the internet", which the model read as "never choose
web_search" — every search became conversation. Treat prompt edits as code
changes and re-measure.

---

## 4. Security model

Four layers, all in `security/`.

**SecurityCore** (`gate.py`) owns one piece of state: whether internet is on.
Every session starts OFF (`reset_session`), and that invariant survives all of
the frontend work. `force_off()` is the kill switch.

**The internet gate** (`check_internet`) is consulted before any web action.
With `ask_before_web` off (default) a web action proceeds and turns internet on,
logged with source `web_action`. With it on, every web action asks first.

**Confirmations** (`core/prompt.py`) are pluggable. WRECZ's prompts were written
as `input()` calls, which would hang forever inside a server process where stdin
belongs to uvicorn. `ask_confirmation` routes to whichever channel is installed:
the terminal by default, the WebSocket when the bridge sets one. The provider is
thread-local, so one request's channel cannot leak into another or into the CLI.

Denial is the default everywhere: an undeliverable prompt, a provider error, a
120-second timeout and a dropped connection all deny.

**SecurityPolicy** (`policy.py`) classifies filesystem actions SAFE / CONFIRM /
BLOCKED. **ActivityLogger** (`logger.py`) appends every decision to
`logs/wrecz_activity.jsonl` — this is usage history and is gitignored.
**SecurityTray** (`tray.py`) shows red/green in the notification area and offers
a manual toggle and emergency off. It runs on a daemon thread inside the bridge
process, so it dies with it — the shell deliberately adds no tray icon of its own.

Application launching is not name-based trust: `application_discovery.py`
resolves a name against the registry, PATH, Start apps and Start menu shortcuts,
and `window_manager.py` only closes windows WRECZ owns or can verify.
Discovery costs 2–4 s and is uncached, so it is not usable on a hot path.

---

## 5. Voice and the visualizer

Kokoro generates a whole sentence at a time, but `voice/kokoro.py` writes
playback in **512-sample slices**. `stream.write` blocks until the audio device
accepts each slice, so the `on_audio` callback is paced by the speakers rather
than by a timer. That is what keeps the waveform in step with what is heard —
measured end to end at a pacing ratio of 1.01.

Each slice is forwarded as uint8 centred on 128, the same encoding
`AnalyserNode.getByteTimeDomainData` produces, so the frontend feeds it to the
visualiser unchanged. Frames are fire-and-forget and dropped past
`MAX_VOICE_FRAMES_IN_FLIGHT`: a stuttering waveform beats stuttering speech.

`on_audio` defaults to `None`, so the CLI path is unchanged.

On the frontend, audio lands in a ring buffer (`src/lib/voiceStream.ts`) and
never passes through React state — 47 frames a second would otherwise re-render
the app. `VoiceVisualizer.tsx` draws every state on one canvas through a single
stroke function, so the line never changes weight and waking up is a continuous
animation rather than an element swap.

---

## 6. Concurrency

- **One request at a time.** `WreczRuntime.request_lock` serialises whole
  requests, because the Router and realtime TTS both touch Windows and audio
  resources. A parked confirmation holds this lock, which is why it times out.
- **Blocking work on worker threads.** `asyncio.to_thread` for `process` and
  for `voice.speak`, so the event loop keeps serving the socket.
- **Cross-thread sends.** `ClientChannel.send_threadsafe` schedules onto the
  loop and waits; `send_voice` schedules and does not wait. All sends serialise
  through one `asyncio.Lock`.
- **Confirmations** bridge the two worlds: a `threading.Event` the worker waits
  on, set by the event loop when the answer frame arrives.

---

## 7. Invariants worth not breaking

1. Internet is OFF at the start of every session.
2. A confirmation that cannot be delivered or answered is a denial.
3. `main.py` behaves as it always did; frontend features default to CLI
   behaviour.
4. Voice failure never breaks the agent — TTS errors are caught and logged.
5. The visualizer never delays speech.
6. The bridge is localhost-only, with an explicit CORS allow list.

---

## 8. Module map

```
wrecz/
  api_server.py       FastAPI bridge: REST, WebSocket, voice streaming
  main.py             original CLI entry point
  run_all.py          launcher for the browser path
  test_bridge.py      WebSocket contract, incl. the confirmation round trip
  core/
    brain.py          intent routing: rules, then the model
    conversation.py   short rolling memory for pronoun/relative references
    router.py         command -> skill, with the security checks
    prompt.py         pluggable confirmation channel
    settings.py       ask_before_web, confirm_destructive
  security/
    gate.py           SecurityCore: internet state, the gate, kill switch
    policy.py         filesystem risk classification
    logger.py         JSONL activity log
    tray.py           notification-area indicator
    application_discovery.py   resolve a name to a real installed program
    window_manager.py          own/verify windows before closing them
  skills/
    apps.py  files.py  internet.py
    system/ volume.py brightness.py wifi.py bluetooth.py
  voice/
    engine.py         public speak() interface
    kokoro.py         Kokoro pipeline, sliced realtime playback

wrecz-frontend/
  src/
    App.tsx  main.tsx  index.css
    hooks/useWrecz.ts            connection, transcript, status, voice state
    lib/wreczApi.ts              WebSocket + REST client, reconnect
    lib/voiceStream.ts           rolling audio buffer
    components/
      WreczApp.tsx               layout and wiring
      VoiceVisualizer.tsx        the centre-line waveform
      ConversationPanel.tsx  Transcript.tsx
      ConfirmPrompt.tsx          answers security prompts
      Panels.tsx  Toggle.tsx  Dropdown.tsx  Triangle.tsx
      WindowControls.tsx         frameless window buttons
    imports/                     Figma-generated assets
  src-tauri/
    src/lib.rs                   window + bridge lifecycle, port guard
    tauri.conf.json              window, CSP, dev wiring
```

### The assurance layer

Five modules ran in mid-August, were disconnected, and are now wired back in:

- `security/safety.py` — `ActionSafety` grades every action SAFE / REVERSIBLE /
  MODIFYING / DESTRUCTIVE / BLOCKED and is the single authority on whether a
  confirmation is required. It runs first in `Router.execute`, so the risk
  level is recorded even for actions that never execute, and it is attached to
  the confirmation prompt so the UI can show severity.
- `security/verification.py` — `VerificationCore` answers "did the requested
  state actually occur?". It returns **three** values: True (checked, correct),
  False (checked, wrong) and **None (no verifier exists)**. None is not a
  failure. Returning False for unhandled actions is what previously made
  volume, brightness, Wi-Fi and Bluetooth announce failure after working.
- `core/executor.py` — `ActionExecutor` runs an operation, logs
  `ACTION_STARTED`, catches exceptions, verifies, and logs one of
  `ACTION_VERIFIED` / `ACTION_VERIFICATION_FAILED` / `ACTION_EXECUTED`.
  Every executing branch of the Router goes through it, so nothing logs
  `ACTION_RESULT` twice.
- `security/application_trust.py` — a second opinion before a launch.
  Discovery decides *which* program a name means; trust decides whether it is
  safe to run. It is the only check that rejects a symlinked executable.
- `core/response.py` — turns the Router's terse result into something worth
  speaking. Failures pass through verbatim.

Actions with no verifier — volume, brightness, Wi-Fi, Bluetooth — execute and
log `ACTION_EXECUTED`. Adding real verifiers for them is a natural next step:
`get_wifi_status` and `get_bluetooth_status` already exist and are exact.

`USER_COMMAND` and `BRAIN_DECISION` had never been emitted by any version of
WRECZ, despite the logger offering them. Both entry points now do, so the log
records what was asked as well as what was done.

---

## 9. Where to change things

| Goal | Start here |
| --- | --- |
| A new spoken/typed command | `core/brain.py` intents, then `core/router.py`, then a skill |
| Recognise a new phrasing | `_local_intent` / `_web_search_intent` in `core/brain.py` |
| Change how the model decides | `CLASSIFIER_PROMPT` in `core/brain.py` — then re-measure |
| A new UI control backed by state | `core/settings.py`, `/api/settings`, `Panels.tsx` |
| Change the security posture | `security/gate.py`, `security/policy.py` |
| Change the voice | `voice/kokoro.py` |
| Change the waveform | `src/components/VoiceVisualizer.tsx` |
| Add a bridge message type | `api_server.py`, `src/lib/wreczApi.ts`, `test_bridge.py` |
| Window, icon, packaging | `src-tauri/` and `DESKTOP.md` |

Two habits this codebase rewards: `python test_bridge.py` after touching the
bridge, and actually measuring intent changes rather than assuming — the
prompt regression in §3 was invisible without it.
