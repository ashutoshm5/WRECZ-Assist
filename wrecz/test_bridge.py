"""Smoke test for the WRECZ frontend bridge.

Exercises the WebSocket contract the frontend depends on, including the
security confirmation round trip, without loading the brain, the Router,
the tray or Kokoro.

    python test_bridge.py
"""

import base64
import math
import threading
import types

import numpy as np
from fastapi.testclient import TestClient

import api_server
from core.prompt import ask_confirmation, confirm_provider
from core.settings import SETTINGS


class StubRuntime:
    """Mirrors WreczRuntime's contract with no Windows or model side effects."""

    def __init__(self):
        self.request_lock = threading.Lock()
        self.internet = False
        self.spoken = []
        self.voice = types.SimpleNamespace(speak=self.speak)

    def speak(self, text, on_audio=None):
        """Stands in for Kokoro: emit a 440Hz tone in slices, as playback would."""
        self.spoken.append(text)

        if on_audio is None:
            return True

        sample_rate = 24000
        for index in range(4):
            start = index * 512
            piece = np.array(
                [
                    math.sin(2 * math.pi * 440 * (start + n) / sample_rate) * 0.5
                    for n in range(512)
                ],
                dtype=np.float32,
            )
            on_audio(piece, sample_rate)

        return True

    def status(self):
        return {
            "internet_enabled": self.internet,
            "status": "ONLINE" if self.internet else "OFFLINE",
        }

    def set_internet(self, enabled):
        self.internet = bool(enabled)
        return self.status()

    def process(self, text, confirmations=None):
        with self.request_lock:
            with confirm_provider(confirmations):
                if text == "close chrome":
                    # Stands in for Router.execute reaching its confirmation.
                    allowed = ask_confirmation(
                        kind="action",
                        question="Allow this action?",
                        action="close_app",
                        target="chrome",
                        reason="The user wants to close an application.",
                    )

                    result = "Closed chrome." if allowed else "Action cancelled."
                    return result, {"intent": "close_application", "action": "close_app"}, True

                return f"echo: {text}", {"intent": "conversation", "action": "conversation"}, True


def collect(socket, stop_type, limit=12):
    """Read frames until stop_type arrives."""
    received = []

    for _ in range(limit):
        frame = socket.receive_json()
        received.append(frame)

        if frame["type"] == stop_type:
            return received

    raise AssertionError(f"never received {stop_type!r}; got {received}")


def types_of(frames):
    return [frame["type"] for frame in frames]


def main():
    api_server.WreczRuntime = StubRuntime

    failures = []

    def check(name, condition, detail=""):
        if condition:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name} {detail}")
            failures.append(name)

    with TestClient(api_server.app) as client:
        print("health / status")
        check("health ok", client.get("/api/health").json() == {"status": "ok"})
        check("status starts offline", client.get("/api/status").json()["status"] == "OFFLINE")

        print("settings")
        check("defaults preserved", client.get("/api/settings").json() == {
            "ask_before_web": False,
            "confirm_destructive": True,
        })

        saved = client.post("/api/settings", json={"ask_before_web": True}).json()
        check("setting written", saved["ask_before_web"] is True)
        check("other setting untouched", saved["confirm_destructive"] is True)
        check("router sees it", SETTINGS.ask_before_web is True)
        client.post("/api/settings", json={"ask_before_web": False})

        with client.websocket_connect("/ws") as socket:
            print("handshake")
            ready = socket.receive_json()
            check("ready frame", ready["type"] == "ready")
            check("ready carries status", ready["status"]["status"] == "OFFLINE")
            check("ready carries settings", ready["settings"]["confirm_destructive"] is True)

            print("plain message")
            socket.send_json({"type": "message", "text": "hello"})
            frames = collect(socket, "state")
            frames = frames if frames[-1]["busy"] is False else frames
            while frames[-1].get("busy") is not False:
                frames += collect(socket, "state")

            kinds = types_of(frames)
            response = next(f for f in frames if f["type"] == "response")
            check("busy announced", frames[0] == {"type": "state", "busy": True})
            check("response returned", response["text"] == "echo: hello")
            check("status follows response", "status" in kinds)
            check("busy cleared", frames[-1] == {"type": "state", "busy": False})

            print("confirmation allowed")
            socket.send_json({"type": "message", "text": "close chrome"})
            frames = collect(socket, "confirm")
            prompt = frames[-1]
            check("confirm delivered", prompt["type"] == "confirm")
            check("confirm carries action", prompt["action"] == "close_app")
            check("confirm carries target", prompt["target"] == "chrome")

            socket.send_json({"type": "confirm", "id": prompt["id"], "allowed": True})
            frames = collect(socket, "response")
            check("allow executes", frames[-1]["text"] == "Closed chrome.")
            collect(socket, "state")

            print("confirmation denied")
            socket.send_json({"type": "message", "text": "close chrome"})
            prompt = collect(socket, "confirm")[-1]
            socket.send_json({"type": "confirm", "id": prompt["id"], "allowed": False})
            frames = collect(socket, "response")
            check("deny cancels", frames[-1]["text"] == "Action cancelled.")
            collect(socket, "state")

            print("stale confirmation")
            socket.send_json({"type": "confirm", "id": "does-not-exist", "allowed": True})
            frame = socket.receive_json()
            check("stale answer reported", frame["type"] == "confirm_closed")
            check("marked expired", frame["resolution"] == "expired")

            print("voice stream")
            socket.send_json({"type": "message", "text": "hello"})

            frames = []
            for _ in range(40):
                frame = socket.receive_json()
                frames.append(frame)
                if frame["type"] == "state" and frame.get("busy") is False:
                    break

            voice = [f for f in frames if f["type"] == "voice"]
            kinds = [f.get("event") for f in voice]

            check("voice start sent", kinds and kinds[0] == "start")
            check("voice stop sent", kinds and kinds[-1] == "stop")
            check("sample rate advertised", voice[0].get("sample_rate") == 24000)

            audio = [f for f in voice if f["event"] == "samples"]
            check("audio frames streamed", len(audio) > 0, f"got {len(audio)}")

            decoded = b"".join(base64.b64decode(f["data"]) for f in audio)
            check("audio is uint8 PCM", len(decoded) == len(audio) * 512,
                  f"{len(decoded)} bytes over {len(audio)} frames")

            values = np.frombuffer(decoded, dtype=np.uint8).astype(np.int16) - 128
            check("audio is centred on silence", abs(values.mean()) < 8,
                  f"mean offset {values.mean():.2f}")
            check("audio carries signal", values.max() > 40 and values.min() < -40,
                  f"range {values.min()}..{values.max()}")

            order = [
                (f["type"], f.get("event"), f.get("busy")) for f in frames
            ]
            i_response = next(i for i, f in enumerate(order) if f[0] == "response")
            i_start = next(i for i, f in enumerate(order) if f[1] == "start")
            i_stop = next(i for i, f in enumerate(order) if f[1] == "stop")
            i_idle = next(i for i, f in enumerate(order) if f[0] == "state" and f[2] is False)
            sample_positions = [i for i, f in enumerate(order) if f[1] == "samples"]

            check("text arrives before speech", i_response < i_start)
            check("samples bracketed by start/stop",
                  all(i_start < i < i_stop for i in sample_positions))
            check("speech finishes before idle", i_stop < i_idle)

            print("internet toggle")
            check("rest toggle on", client.post("/api/internet", json={"enabled": True}).json()["status"] == "ONLINE")
            broadcastframe = socket.receive_json()
            check("toggle broadcast", broadcastframe["type"] == "status")
            check("broadcast is online", broadcastframe["status"]["internet_enabled"] is True)
            client.post("/api/internet", json={"enabled": False})
            socket.receive_json()

            print("protocol")
            socket.send_json({"type": "ping"})
            check("ping answered", socket.receive_json()["type"] == "pong")

            socket.send_json({"type": "nonsense"})
            check("unknown type rejected", socket.receive_json()["type"] == "error")

            socket.send_json({"type": "message", "text": "   "})
            socket.send_json({"type": "ping"})
            check("blank message ignored", socket.receive_json()["type"] == "pong")

    print()

    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        raise SystemExit(1)

    print("Bridge contract OK.")


if __name__ == "__main__":
    main()
