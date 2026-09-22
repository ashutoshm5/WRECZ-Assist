WRECZ VOICE INTEGRATION — PASS 5

This package keeps the existing WRECZ behavior and changes only the
new voice output path from file-based playback to realtime playback.

PRESERVED FROM THE EXISTING WRECZ MAIN:
- SecurityCore initialization
- Internet session reset
- Startup internet permission
- SecurityTray
- Router initialization
- Security status command
- Manual internet on/off commands
- Brain input
- Brain command display
- Router execution
- Router result display
- Tray refresh
- KeyboardInterrupt handling
- Existing top-level error handling
- PyTorch preload required for the Windows c10.dll/WinRT conflict

VOICE:
- Engine: Kokoro
- Voice: am_fenrir
- Speed: 0.94
- WRECZ pronunciation override: wraekkkzzzz

REALTIME OUTPUT:
Kokoro produces audio chunks and sends each chunk directly to the
Windows audio output through sounddevice. No WAV or temporary audio
file is written to disk.

REQUIREMENTS:
Use the Python 3.12 WRECZ virtual environment.

Install/check:
    pip install kokoro soundfile
    pip install "misaki[en]"
    pip install sounddevice

VOICE-ONLY TEST:
    python test_voice.py

The test should speak immediately as Kokoro produces audio chunks and
should finish with:
    Realtime voice test complete.
    No audio file was created.

RUN WRECZ:
    python main.py

EXAMPLE:
    You: open chrome

WRECZ continues its existing flow:
    Brain -> Router -> existing security/executor flow
    Router result -> Kokoro -> realtime audio output

IMPORTANT:
Voice failure remains isolated. If TTS fails, WRECZ prints
[VOICE] TTS unavailable and continues running the existing agent.

The frontend waveform is not modified in this pass. The audio stream
can later be routed through the FastAPI/WebSocket bridge so the same
realtime audio can feed both the speakers and the locked visualizer.

LOW-LATENCY VOICE BEHAVIOR
- Kokoro is warmed up once during startup to avoid first-response model-load latency.
- For non-confirmation open_app and close_app actions, a short voice acknowledgment is started concurrently with Router execution.
- Realtime audio is still streamed directly to the speakers; no WAV response file is created.
- Confirmation-required actions retain the original Router confirmation flow and speak only after execution.

PASS 8 - GENERIC RESULT VOICE
-----------------------------
Voice output is now completely generic. main.py does not enumerate commands,
actions, applications, volume controls, or future features. After Router
execution, whatever result string the Router returns is passed directly to the
realtime VoiceEngine.

This means a new WRECZ feature only needs to return its normal result; no new
voice-specific branch is required.

Important latency behavior:
- Kokoro remains preloaded at startup.
- Audio remains streamed directly to the speakers.
- No WAV file is created.
- The actual Router result is spoken, so WRECZ never speaks a guessed or
  hardcoded acknowledgement before the operation completes.
