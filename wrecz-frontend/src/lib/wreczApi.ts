/**
 * Client for the local WRECZ bridge (api_server.py).
 *
 * Transport split:
 *   WebSocket - conversation and security confirmations, which are a
 *               round trip: WRECZ asks, the UI answers, the request resumes.
 *   HTTP      - status and settings, which are plain reads and writes.
 */

const HOST = "127.0.0.1:8765";
const API_URL = `http://${HOST}/api`;
const WS_URL = `ws://${HOST}/ws`;

export type SecurityStatus = {
  internet_enabled: boolean;
  status: string;
};

export type WreczSettings = {
  ask_before_web: boolean;
  confirm_destructive: boolean;
};

/** A security prompt WRECZ is blocked on until the user answers. */
export type ConfirmRequest = {
  id: string;
  kind: "action" | "file" | "internet" | string;
  question: string;
  action: string;
  target: string;
  reason: string;
};

export type ServerMessage =
  | { type: "ready"; text: string; status: SecurityStatus; settings: WreczSettings }
  | { type: "response"; text: string; intent?: string; action?: string }
  | { type: "status"; status: SecurityStatus }
  | { type: "settings"; settings: WreczSettings }
  | { type: "state"; busy: boolean }
  | ({ type: "confirm" } & ConfirmRequest)
  | { type: "confirm_closed"; id: string; resolution: "timeout" | "expired" }
  | { type: "voice"; event: "start"; sample_rate: number }
  | { type: "voice"; event: "samples"; data: string }
  | { type: "voice"; event: "stop" }
  | { type: "error"; message: string }
  | { type: "pong" };

export type ConnectionState = "connecting" | "online" | "offline";

export type WreczHandlers = {
  onMessage: (message: ServerMessage) => void;
  onConnectionChange: (state: ConnectionState) => void;
};

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 10000;

export class WreczClient {
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private attempts = 0;
  private disposed = false;

  constructor(private readonly handlers: WreczHandlers) {}

  connect() {
    if (this.disposed) return;

    this.clearTimer();
    this.handlers.onConnectionChange("connecting");

    const socket = new WebSocket(WS_URL);
    this.socket = socket;

    socket.addEventListener("open", () => {
      this.attempts = 0;
      this.handlers.onConnectionChange("online");
    });

    socket.addEventListener("message", (event) => {
      let parsed: ServerMessage;

      try {
        parsed = JSON.parse(event.data) as ServerMessage;
      } catch {
        this.handlers.onMessage({
          type: "error",
          message: "WRECZ returned a response that could not be read.",
        });
        return;
      }

      this.handlers.onMessage(parsed);
    });

    socket.addEventListener("close", () => {
      if (this.socket === socket) this.socket = null;
      if (this.disposed) return;

      this.handlers.onConnectionChange("offline");
      this.scheduleReconnect();
    });

    // "error" is always followed by "close", so reconnection is handled there.
    socket.addEventListener("error", () => {
      if (this.disposed) return;
      this.handlers.onConnectionChange("offline");
    });
  }

  private scheduleReconnect() {
    if (this.disposed || this.reconnectTimer !== null) return;

    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** this.attempts,
      RECONNECT_MAX_MS,
    );

    this.attempts += 1;

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private clearTimer() {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private post(payload: unknown): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return false;

    this.socket.send(JSON.stringify(payload));
    return true;
  }

  send(text: string): boolean {
    return this.post({ type: "message", text });
  }

  answerConfirm(id: string, allowed: boolean): boolean {
    return this.post({ type: "confirm", id, allowed });
  }

  dispose() {
    // Set before closing: the close listener reads this to tell an
    // intentional teardown from a dropped connection worth reconnecting.
    this.disposed = true;
    this.clearTimer();

    const socket = this.socket;
    this.socket = null;
    socket?.close();
  }
}

async function readJson<T>(response: Response, failure: string): Promise<T> {
  if (!response.ok) throw new Error(failure);
  return (await response.json()) as T;
}

export async function getSecurityStatus(): Promise<SecurityStatus> {
  return readJson<SecurityStatus>(
    await fetch(`${API_URL}/status`),
    "Unable to read WRECZ security status.",
  );
}

export async function setInternetAccess(enabled: boolean): Promise<SecurityStatus> {
  return readJson<SecurityStatus>(
    await fetch(`${API_URL}/internet`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
    "Unable to change internet access.",
  );
}

export async function getSettings(): Promise<WreczSettings> {
  return readJson<WreczSettings>(
    await fetch(`${API_URL}/settings`),
    "Unable to read WRECZ settings.",
  );
}

export async function updateSettings(
  changes: Partial<WreczSettings>,
): Promise<WreczSettings> {
  return readJson<WreczSettings>(
    await fetch(`${API_URL}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }),
    "Unable to change WRECZ settings.",
  );
}
