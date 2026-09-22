import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  WreczClient,
  getSecurityStatus,
  getSettings,
  setInternetAccess,
  updateSettings,
  type ConfirmRequest,
  type ConnectionState,
  type SecurityStatus,
  type ServerMessage,
  type WreczSettings,
} from "@/lib/wreczApi";
import { VoiceStream, decodeVoiceFrame } from "@/lib/voiceStream";

export type TranscriptRole = "you" | "wrecz" | "system";

export type TranscriptEntry = {
  id: number;
  role: TranscriptRole;
  text: string;
};

/** The tray and the chat can both change internet state behind our back. */
const STATUS_POLL_MS = 5000;

let entryId = 0;

export function useWrecz() {
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [settings, setSettings] = useState<WreczSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [confirms, setConfirms] = useState<ConfirmRequest[]>([]);

  const clientRef = useRef<WreczClient | null>(null);

  // Audio arrives ~47 times a second. It goes straight into this buffer and
  // never through React state, so speech does not re-render the app.
  const voiceRef = useRef<VoiceStream | null>(null);
  if (voiceRef.current === null) voiceRef.current = new VoiceStream();
  const voice = voiceRef.current;

  // Guards setSpeaking so 47 audio frames a second do not each try to
  // re-render the app.
  const speakingRef = useRef(false);

  const append = useCallback((role: TranscriptRole, text: string) => {
    entryId += 1;
    const entry = { id: entryId, role, text };
    setTranscript((current) => [...current, entry]);
  }, []);

  const handleMessage = useCallback(
    (message: ServerMessage) => {
      switch (message.type) {
        case "ready":
          setStatus(message.status);
          setSettings(message.settings);
          break;

        case "response":
          if (message.text) append("wrecz", message.text);
          break;

        case "status":
          setStatus(message.status);
          break;

        case "settings":
          setSettings(message.settings);
          break;

        case "state":
          setBusy(message.busy);
          break;

        case "confirm":
          setConfirms((current) => [
            ...current,
            {
              id: message.id,
              kind: message.kind,
              question: message.question,
              action: message.action,
              target: message.target,
              reason: message.reason,
            },
          ]);
          break;

        case "confirm_closed":
          setConfirms((current) => current.filter((item) => item.id !== message.id));
          append(
            "system",
            message.resolution === "timeout"
              ? "The security prompt timed out and the action was denied."
              : "That security prompt is no longer waiting for an answer.",
          );
          break;

        case "voice":
          if (message.event === "start") {
            // Kokoro needs a second or two to generate before any audio
            // exists, so arm here but stay flat until real samples land.
            voice.reset();
            speakingRef.current = false;
          } else if (message.event === "samples") {
            voice.push(decodeVoiceFrame(message.data));

            if (!speakingRef.current) {
              speakingRef.current = true;
              setSpeaking(true);
            }
          } else {
            speakingRef.current = false;
            setSpeaking(false);
          }
          break;

        case "error":
          append("system", message.message);
          break;

        default:
          break;
      }
    },
    [append, voice],
  );

  // Keep the live handler out of the socket's dependency list so a re-render
  // never tears down and reconnects the connection.
  const handlerRef = useRef(handleMessage);
  handlerRef.current = handleMessage;

  useEffect(() => {
    const client = new WreczClient({
      onMessage: (message) => handlerRef.current(message),
      onConnectionChange: (next) => {
        setConnection(next);

        if (next !== "online") {
          // A dropped socket abandons whatever WRECZ was waiting on.
          setBusy(false);
          speakingRef.current = false;
          setSpeaking(false);
          setConfirms([]);
        }
      },
    });

    clientRef.current = client;
    client.connect();

    return () => {
      client.dispose();
      clientRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (connection !== "online") return;

    let cancelled = false;

    const sync = async () => {
      try {
        const [nextStatus, nextSettings] = await Promise.all([
          getSecurityStatus(),
          getSettings(),
        ]);

        if (cancelled) return;

        setStatus(nextStatus);
        setSettings(nextSettings);
      } catch {
        // The socket state is the authoritative health signal; a failed poll
        // on its own is not worth reporting to the user.
      }
    };

    void sync();
    const timer = window.setInterval(sync, STATUS_POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [connection]);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      append("you", trimmed);

      if (!clientRef.current?.send(trimmed)) {
        append("system", "WRECZ is not connected. Start the WRECZ bridge and try again.");
      }
    },
    [append],
  );

  const answerConfirm = useCallback((id: string, allowed: boolean) => {
    setConfirms((current) => current.filter((item) => item.id !== id));
    clientRef.current?.answerConfirm(id, allowed);
  }, []);

  const setInternet = useCallback(
    async (enabled: boolean) => {
      // Reflect the intent immediately, then let the backend confirm it.
      setStatus({
        internet_enabled: enabled,
        status: enabled ? "ONLINE" : "OFFLINE",
      });

      try {
        setStatus(await setInternetAccess(enabled));
      } catch {
        append("system", "WRECZ could not change internet access.");

        try {
          setStatus(await getSecurityStatus());
        } catch {
          setStatus(null);
        }
      }
    },
    [append],
  );

  const changeSetting = useCallback(
    async (key: keyof WreczSettings, value: boolean) => {
      const previous = settings;
      if (previous) setSettings({ ...previous, [key]: value });

      try {
        setSettings(await updateSettings({ [key]: value }));
      } catch {
        append("system", "WRECZ could not save that setting.");
        if (previous) setSettings(previous);
      }
    },
    [append, settings],
  );

  const pendingConfirm = confirms[0] ?? null;

  return useMemo(
    () => ({
      connection,
      transcript,
      status,
      settings,
      busy,
      speaking,
      voice,
      pendingConfirm,
      send,
      answerConfirm,
      setInternet,
      changeSetting,
    }),
    [
      connection,
      transcript,
      status,
      settings,
      busy,
      speaking,
      voice,
      pendingConfirm,
      send,
      answerConfirm,
      setInternet,
      changeSetting,
    ],
  );
}
