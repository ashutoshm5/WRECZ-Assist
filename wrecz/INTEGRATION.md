# WRECZ frontend <-> backend connection

The React frontend (`../wrecz-frontend`) and the WRECZ agent are connected
through `api_server.py`, a localhost-only bridge. The CLI (`main.py`) is
untouched and still runs standalone.

```
wrecz-frontend (Vite, 127.0.0.1:8443)
        |  WebSocket ws://127.0.0.1:8765/ws      conversation + confirmations
        |  HTTP      http://127.0.0.1:8765/api   status + settings
        v
api_server.py -> core.brain -> core.router -> skills/
                 security.gate (SecurityCore) + security.tray
                 voice.VoiceEngine (Kokoro, speaks on this machine)
```

See ARCHITECTURE.md for how the pieces fit together, and requirements.txt
for the Python dependencies.

## Run

```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_all.py
```

Starts the bridge on 8765 and Vite on 8443, installs frontend dependencies on
first run, and shuts both down together. Open http://127.0.0.1:8443.

The two ports are not arbitrary: 8443 is the origin allowed by the bridge's
CORS policy in `api_server.py`.

Ollama must be running for anything the deterministic parsers in
`core/brain.py` do not already handle.

## HTTP

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/health` | GET | Liveness. |
| `/api/status` | GET | `{internet_enabled, status}` from SecurityCore. |
| `/api/internet` | POST | `{enabled}` - Internet Access toggle. |
| `/api/settings` | GET/POST | `{ask_before_web, confirm_destructive}`. |

## WebSocket

Client to server:

| Frame | Meaning |
| --- | --- |
| `{type:"message", text}` | A user message. |
| `{type:"confirm", id, allowed}` | Answer to a pending security prompt. |
| `{type:"ping"}` | Keepalive. |

Server to client:

| Frame | Meaning |
| --- | --- |
| `{type:"ready", text, status, settings}` | Sent on connect. |
| `{type:"state", busy}` | Request started / finished. |
| `{type:"response", text, intent, action}` | The Router's result. |
| `{type:"status", status}` | Authoritative internet state. |
| `{type:"settings", settings}` | Settings changed elsewhere. |
| `{type:"confirm", id, kind, question, action, target, reason}` | WRECZ is blocked awaiting an answer. |
| `{type:"confirm_closed", id, resolution}` | A prompt timed out or expired. |
| `{type:"voice", event:"start", sample_rate}` | Speech is about to begin. |
| `{type:"voice", event:"samples", data}` | One slice of speech audio, base64 uint8. |
| `{type:"voice", event:"stop"}` | Speech finished. |
| `{type:"error", message}` | The request failed. |

## Security confirmations

WRECZ's confirmation prompts were written for the CLI and called `input()`
directly. In a server process stdin belongs to uvicorn, so those calls would
have hung every `close app`, file write and gated web search.

`core/prompt.py` makes the prompt channel injectable. With nothing installed
it still reads the terminal, so `main.py` behaves exactly as before. The
bridge installs a per-request provider that sends a `confirm` frame and parks
the worker thread until the answer arrives on the same socket - which is why
the WebSocket endpoint keeps receiving while a request is in flight.

Denial is the default everywhere: an undeliverable prompt, a provider error,
a 120 second timeout and a dropped connection all deny.

## Settings

Both defaults match WRECZ's existing behaviour, so a session that never opens
the Settings panel behaves as it did before.

- `ask_before_web` (default off) - with it off, a web action such as a search
  runs immediately; the session still starts offline and the first web action
  turns internet on, logged with source `web_action`. With it on, every web
  action asks first. The tray kill switch overrides either way.
- `confirm_destructive` (default on) - `close_app` and write/delete
  filesystem actions require confirmation.

`Internet Access` in the panel is not a setting; it is SecurityCore session
state, and it always starts OFF on a new session.

## Frontend surfaces

The conversation transcript is not on the main view. It opens from the menu
dropdown via "Conversation box"; the menu icon carries an unread dot for
anything that arrived while it was closed. Security confirmations stay on the
main view, since they block a request.

The centre line is the voice visualizer, wired straight to the voice engine.
It is a straight line until WRECZ first speaks, the waveform while it speaks,
and a slow idle wave after that so the assistant reads as awake.

## Voice streaming

`VoiceEngine.speak(text, on_audio=...)` reports each slice of audio as it is
produced. Kokoro emits a whole sentence at a time, so `voice/kokoro.py` writes
playback in 512-sample slices: `stream.write` blocks until the audio device
accepts the data, which paces the callback to real time. Measured end to end,
audio reaches the browser at a pacing ratio of 1.01 against playback.

The bridge forwards each slice as uint8 centred on 128 - the same encoding
`AnalyserNode.getByteTimeDomainData` produces - so the frontend feeds it to
the visualizer unchanged. Audio frames are fire-and-forget and are dropped
past `MAX_VOICE_FRAMES_IN_FLIGHT`: a stuttering waveform beats stuttering
speech. A failing listener detaches itself and speech continues.

`on_audio` defaults to None, so the CLI path in `main.py` is unchanged.

## Tests

```
python test_bridge.py   # WebSocket contract, incl. the confirmation round trip
python test_voice.py    # Kokoro realtime output
```
