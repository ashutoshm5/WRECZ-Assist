import Transcript from "./Transcript";
import type { TranscriptEntry } from "@/hooks/useWrecz";

/**
 * The conversation lives here rather than on the main view, so the workspace
 * stays clear and the transcript is opened deliberately from the menu.
 */
export default function ConversationPanel({
  entries,
  busy,
}: {
  entries: TranscriptEntry[];
  busy: boolean;
}) {
  return (
    <div className="wrecz-conversation-panel" aria-label="Conversation box">
      <div className="wrecz-conversation-header">
        <span>Conversation</span>
        {busy ? <span className="wrecz-conversation-busy">WRECZ is working</span> : null}
      </div>

      <div className="wrecz-conversation-body">
        {entries.length === 0 && !busy ? (
          <p className="wrecz-conversation-empty">No messages yet.</p>
        ) : (
          <Transcript entries={entries} busy={busy} />
        )}
      </div>
    </div>
  );
}
