"""Local WRECZ <-> frontend bridge.

This is an additive API layer. The existing CLI entry point (main.py) is not
replaced or modified. The frontend talks to this process over localhost only.

The WebSocket endpoint keeps receiving while a request is running. That is what
makes WRECZ's security confirmations work in the UI: the Router blocks on a
worker thread waiting for an answer, and the answer arrives over the same
socket as a normal inbound frame.
"""

import asyncio
import base64
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

# Keep the same PyTorch preload used by the existing WRECZ main.py.
import torch  # noqa: F401

import numpy as np

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.brain import ask_wrecz, warm_up as warm_up_brain
from core.response import respond
from core.prompt import confirm_provider
from core.router import Router
from core.settings import SETTINGS
from security.gate import SecurityCore
from security.tray import SecurityTray
from voice import VoiceEngine


# A confirmation the user never answers must not hold the request lock
# forever. Timing out denies the action, matching WRECZ's [y/N] default.
CONFIRM_TIMEOUT_SECONDS = 120.0

# Visualizer frames are cosmetic and must never slow speech down, so they are
# fire-and-forget and dropped once this many are still in flight.
MAX_VOICE_FRAMES_IN_FLIGHT = 8


class InternetRequest(BaseModel):
    enabled: bool


class SettingsRequest(BaseModel):
    ask_before_web: bool | None = None
    confirm_destructive: bool | None = None


class WreczRuntime:
    def __init__(self) -> None:
        self.security = SecurityCore()
        # Preserve WRECZ's security invariant: every new session starts OFF.
        self.security.reset_session()

        self.tray = SecurityTray(self.security)
        self.tray.start()

        self.router = Router(self.security)
        self.voice = VoiceEngine(
            voice="am_fenrir",
            speed=0.94,
        )

        # Router actions and realtime TTS both touch Windows/audio resources.
        # Serialize complete requests so two frontend events cannot overlap.
        self.request_lock = threading.Lock()

        try:
            self.voice.warm_up()
        except Exception as error:
            print("[VOICE] TTS warm-up unavailable:", error)

        # Load the classifier too, so the first command does not pay the
        # ~10s model load on top of everything else.
        warm_up_brain()

    def status(self) -> dict[str, Any]:
        return self.security.get_status()

    def set_internet(self, enabled: bool) -> dict[str, Any]:
        if enabled:
            self.security.enable_internet(source="frontend")
        else:
            self.security.force_off()

        self.tray.refresh()
        return self.status()

    def process(
        self,
        text: str,
        confirmations: Any = None,
    ) -> tuple[str, dict[str, Any], bool]:
        """Process one user message.

        confirmations, when given, receives any security prompt raised while
        this request runs. With none, WRECZ falls back to its CLI prompt.

        Returns (display_text, command, should_speak).
        """
        with self.request_lock:
            with confirm_provider(confirmations):
                return self._process(text)

    def _process(self, text: str) -> tuple[str, dict[str, Any], bool]:
        normalized = text.strip()

        if normalized.lower() == "status":
            status = self.security.get_status()
            display = f"Internet: {status['status']}"
            return display, {"intent": "security_status"}, False

        if normalized.lower() in {
            "internet on",
            "enable internet",
            "turn internet on",
        }:
            self.security.enable_internet(source="frontend_command")
            self.tray.refresh()
            return "Internet access enabled.", {"intent": "enable_internet"}, True

        if normalized.lower() in {
            "internet off",
            "disable internet",
            "turn internet off",
        }:
            self.security.force_off()
            self.tray.refresh()
            return "Internet access disabled.", {"intent": "disable_internet"}, True

        self.security.logger.user_command(normalized)

        command = ask_wrecz(normalized)

        self.security.logger.brain_decision(normalized, command)

        if command.get("action") == "conversation":
            result = str(command.get("response", "")).strip()
        else:
            # respond() turns the Router's terse result into something
            # worth speaking. Failures pass through verbatim.
            result = respond(command, self.router.execute(command))

        self.tray.refresh()
        return result, command, bool(result)


runtime: WreczRuntime | None = None


# =========================================================
# CLIENT CHANNEL
# =========================================================

@dataclass
class _PendingConfirm:
    event: threading.Event
    allowed: bool = False


class ClientChannel:
    """One connected frontend.

    Also acts as the confirmation provider for requests from this client:
    calling the instance is what core.prompt invokes on the worker thread.
    """

    def __init__(self, websocket: WebSocket, loop: asyncio.AbstractEventLoop) -> None:
        self.websocket = websocket
        self.loop = loop
        self.closed = False

        self._send_lock = asyncio.Lock()
        self._pending: dict[str, _PendingConfirm] = {}
        self._pending_lock = threading.Lock()
        self._voice_lock = threading.Lock()
        self._voice_in_flight = 0

    # -----------------------------------------------------
    # SEND
    # -----------------------------------------------------

    async def send(self, payload: dict[str, Any]) -> bool:
        if self.closed:
            return False

        async with self._send_lock:
            try:
                await self.websocket.send_json(payload)
                return True
            except Exception:
                self.closed = True
                return False

    def send_threadsafe(self, payload: dict[str, Any]) -> bool:
        """Send from a worker thread by scheduling onto the event loop."""
        if self.closed:
            return False

        try:
            future = asyncio.run_coroutine_threadsafe(
                self.send(payload),
                self.loop,
            )
            return bool(future.result(timeout=10.0))
        except Exception:
            return False

    # -----------------------------------------------------
    # VOICE STREAM (audio thread)
    # -----------------------------------------------------

    def send_voice(self, samples: Any) -> None:
        """Forward one slice of speech audio without blocking playback.

        Called from the Kokoro playback thread between writes to the audio
        device, so it must return immediately. Frames are dropped rather than
        queued without limit: a stuttering waveform is always better than
        stuttering speech.
        """
        if self.closed:
            return

        with self._voice_lock:
            if self._voice_in_flight >= MAX_VOICE_FRAMES_IN_FLIGHT:
                return
            self._voice_in_flight += 1

        # float32 [-1, 1] -> uint8 centred on 128, the same encoding the
        # browser's AnalyserNode.getByteTimeDomainData produces.
        block = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
        encoded = base64.b64encode(
            (block * 127.0 + 128.0).astype(np.uint8).tobytes()
        ).decode("ascii")

        async def deliver() -> None:
            try:
                await self.send({
                    "type": "voice",
                    "event": "samples",
                    "data": encoded,
                })
            finally:
                with self._voice_lock:
                    self._voice_in_flight -= 1

        try:
            asyncio.run_coroutine_threadsafe(deliver(), self.loop)
        except Exception:
            with self._voice_lock:
                self._voice_in_flight -= 1

    # -----------------------------------------------------
    # CONFIRMATION PROVIDER (worker thread)
    # -----------------------------------------------------

    def __call__(self, request: Any) -> bool:
        request_id = uuid.uuid4().hex
        pending = _PendingConfirm(event=threading.Event())

        with self._pending_lock:
            self._pending[request_id] = pending

        try:
            delivered = self.send_threadsafe({
                "type": "confirm",
                "id": request_id,
                "kind": request.kind,
                "question": request.question,
                "action": request.action,
                "target": request.target,
                "reason": request.reason,
            })

            if not delivered:
                print("[SECURITY] Confirmation could not be delivered. Denying.")
                return False

            if not pending.event.wait(CONFIRM_TIMEOUT_SECONDS):
                print("[SECURITY] Confirmation timed out. Denying.")
                self.send_threadsafe({
                    "type": "confirm_closed",
                    "id": request_id,
                    "resolution": "timeout",
                })
                return False

            return pending.allowed

        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    # -----------------------------------------------------
    # RESOLUTION (event loop thread)
    # -----------------------------------------------------

    def resolve(self, request_id: str, allowed: bool) -> bool:
        with self._pending_lock:
            pending = self._pending.get(request_id)

        if pending is None:
            return False

        pending.allowed = allowed
        pending.event.set()
        return True

    def close(self) -> None:
        """Deny anything still waiting so no worker thread is left blocked."""
        self.closed = True

        with self._pending_lock:
            waiting = list(self._pending.values())

        for pending in waiting:
            pending.allowed = False
            pending.event.set()


VOICE_SAMPLE_RATE = 24000


def speak_streaming(channel: ClientChannel, text: str) -> None:
    """Speak text while forwarding the audio to the client's visualizer."""
    get_runtime().voice.speak(
        text,
        on_audio=lambda samples, _rate: channel.send_voice(samples),
    )


CHANNELS: set[ClientChannel] = set()


async def broadcast(payload: dict[str, Any]) -> None:
    for channel in list(CHANNELS):
        await channel.send(payload)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global runtime
    runtime = WreczRuntime()
    print("WRECZ API bridge: READY on 127.0.0.1:8765")
    yield


app = FastAPI(
    title="WRECZ Local Bridge",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Browser / Vite dev server.
        "http://127.0.0.1:8443",
        "http://localhost:8443",
        # Tauri desktop shell. Windows serves the app from http://tauri.localhost;
        # the tauri:// form is macOS and Linux.
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_runtime() -> WreczRuntime:
    if runtime is None:
        raise RuntimeError("WRECZ runtime is not initialized.")
    return runtime


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, Any]:
    return get_runtime().status()


@app.post("/api/internet")
async def internet(request: InternetRequest) -> dict[str, Any]:
    current = get_runtime().set_internet(request.enabled)

    # Keep every open view in step, including the one that did not ask.
    await broadcast({"type": "status", "status": current})
    return current


@app.get("/api/settings")
def read_settings() -> dict[str, Any]:
    return SETTINGS.as_dict()


@app.post("/api/settings")
async def write_settings(request: SettingsRequest) -> dict[str, Any]:
    current = SETTINGS.update(**request.model_dump(exclude_none=True))

    await broadcast({"type": "settings", "settings": current})
    return current


# =========================================================
# WEBSOCKET
# =========================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    channel = ClientChannel(websocket, asyncio.get_running_loop())
    CHANNELS.add(channel)

    queue: asyncio.Queue[str] = asyncio.Queue()

    async def handle(text: str) -> None:
        await channel.send({"type": "state", "busy": True})

        try:
            result, command, should_speak = await asyncio.to_thread(
                get_runtime().process,
                text,
                channel,
            )

            # Send the actual response to the UI. The frontend never needs
            # to know the internal command schema.
            await channel.send({
                "type": "response",
                "text": result,
                "intent": command.get("intent"),
                "action": command.get("action"),
            })

            # A request can change internet state (web search, "internet on"),
            # so report the authoritative status with every reply.
            await channel.send({"type": "status", "status": get_runtime().status()})

            # Keep TTS generic: whatever response was actually produced is
            # what Kokoro speaks. No command-specific voice branches.
            if should_speak and result:
                # The visualizer is driven by the voice engine itself, so the
                # waveform moves only while WRECZ is actually speaking.
                await channel.send({
                    "type": "voice",
                    "event": "start",
                    "sample_rate": VOICE_SAMPLE_RATE,
                })

                try:
                    await asyncio.to_thread(speak_streaming, channel, result)
                except Exception as voice_error:
                    print("[VOICE] TTS unavailable:", voice_error)
                finally:
                    await channel.send({"type": "voice", "event": "stop"})

        except Exception as error:
            print("[API ERROR]", error)
            await channel.send({
                "type": "error",
                "message": "WRECZ could not complete that request.",
            })

        finally:
            await channel.send({"type": "state", "busy": False})

    async def worker() -> None:
        while True:
            text = await queue.get()
            try:
                await handle(text)
            finally:
                queue.task_done()

    worker_task = asyncio.create_task(worker())

    try:
        await channel.send({
            "type": "ready",
            "text": "WRECZ is ready.",
            "status": get_runtime().status(),
            "settings": SETTINGS.as_dict(),
        })

        while True:
            payload = await websocket.receive_json()
            message_type = payload.get("type")

            if message_type == "message":
                text = str(payload.get("text", "")).strip()
                if text:
                    await queue.put(text)

            elif message_type == "confirm":
                # Answering a pending security prompt. This is why the receive
                # loop must never be blocked by the request it is answering.
                resolved = channel.resolve(
                    str(payload.get("id", "")),
                    bool(payload.get("allowed", False)),
                )

                if not resolved:
                    await channel.send({
                        "type": "confirm_closed",
                        "id": str(payload.get("id", "")),
                        "resolution": "expired",
                    })

            elif message_type == "ping":
                await channel.send({"type": "pong"})

            else:
                await channel.send({
                    "type": "error",
                    "message": "Unknown WRECZ message type.",
                })

    except WebSocketDisconnect:
        pass

    except Exception as error:
        print("[API ERROR] WebSocket closed:", error)

    finally:
        # Release any worker thread parked on a confirmation before tearing
        # the connection down, otherwise it would hold the request lock.
        channel.close()
        worker_task.cancel()
        CHANNELS.discard(channel)
