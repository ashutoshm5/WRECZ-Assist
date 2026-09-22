import { useEffect, useRef } from "react";
import type { TranscriptEntry } from "@/hooks/useWrecz";

const ROLE_LABEL: Record<TranscriptEntry["role"], string> = {
  you: "You",
  wrecz: "WRECZ",
  system: "Security",
};

export default function Transcript({
  entries,
  busy,
}: {
  entries: TranscriptEntry[];
  busy: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [entries, busy]);

  return (
    <div className="wrecz-transcript" aria-live="polite" aria-label="Conversation">
      {entries.map((entry) => (
        <div key={entry.id} className={`wrecz-entry wrecz-entry--${entry.role}`}>
          <span className="wrecz-entry-role">{ROLE_LABEL[entry.role]}</span>
          <p className="wrecz-entry-text">{entry.text}</p>
        </div>
      ))}

      {busy ? (
        <div className="wrecz-entry wrecz-entry--wrecz">
          <span className="wrecz-entry-role">WRECZ</span>
          <p className="wrecz-entry-text wrecz-entry-text--busy">Working</p>
        </div>
      ) : null}

      <div ref={endRef} />
    </div>
  );
}
