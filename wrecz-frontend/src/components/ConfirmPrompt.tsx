import { useEffect, useRef } from "react";
import type { ConfirmRequest } from "@/lib/wreczApi";

const KIND_LABEL: Record<string, string> = {
  action: "Action confirmation",
  file: "File operation",
  internet: "Internet access",
};

/**
 * WRECZ is blocked on this answer: the Router is parked on a worker thread
 * until one of these buttons is pressed. Denying is the safe default, so
 * Escape and an unanswered prompt both mean deny.
 */
export default function ConfirmPrompt({
  request,
  onAnswer,
}: {
  request: ConfirmRequest;
  onAnswer: (id: string, allowed: boolean) => void;
}) {
  const allowRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    allowRef.current?.focus();
  }, [request.id]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onAnswer(request.id, false);
      }
    };

    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [request.id, onAnswer]);

  const detail = [request.action, request.target].filter(Boolean).join(" · ");

  return (
    <div className="wrecz-confirm" role="alertdialog" aria-label={request.question}>
      <span className="wrecz-confirm-kind">{KIND_LABEL[request.kind] ?? "Confirmation"}</span>

      <p className="wrecz-confirm-question">{request.question}</p>

      {detail ? <p className="wrecz-confirm-detail">{detail}</p> : null}
      {request.reason ? <p className="wrecz-confirm-reason">{request.reason}</p> : null}

      <div className="wrecz-confirm-actions">
        <button
          type="button"
          className="wrecz-confirm-deny"
          onClick={() => onAnswer(request.id, false)}
        >
          Deny
        </button>

        <button
          ref={allowRef}
          type="button"
          className="wrecz-confirm-allow"
          onClick={() => onAnswer(request.id, true)}
        >
          Allow
        </button>
      </div>
    </div>
  );
}
