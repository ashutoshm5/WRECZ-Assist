import { useEffect, useState } from "react";

/**
 * Window controls for the frameless desktop shell.
 *
 * The design has no title bar, so the window runs with decorations off and
 * supplies its own controls. Renders nothing in a plain browser tab, where
 * the browser already provides them.
 */

function inTauri() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function currentWindow() {
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  return getCurrentWindow();
}

export default function WindowControls() {
  const [desktop, setDesktop] = useState(false);

  // Detect after mount so the browser build renders identically on the server
  // and the client.
  useEffect(() => setDesktop(inTauri()), []);

  if (!desktop) return null;

  return (
    <div className="wrecz-window-controls">
      <button
        type="button"
        aria-label="Minimise"
        onClick={() => void currentWindow().then((w) => w.minimize())}
      >
        <svg viewBox="0 0 10 10" aria-hidden="true">
          <path d="M1 5h8" />
        </svg>
      </button>

      <button
        type="button"
        aria-label="Maximise"
        onClick={() => void currentWindow().then((w) => w.toggleMaximize())}
      >
        <svg viewBox="0 0 10 10" aria-hidden="true">
          <rect x="1.2" y="1.2" width="7.6" height="7.6" />
        </svg>
      </button>

      <button
        type="button"
        className="wrecz-window-close"
        aria-label="Close"
        onClick={() => void currentWindow().then((w) => w.close())}
      >
        <svg viewBox="0 0 10 10" aria-hidden="true">
          <path d="M1.4 1.4l7.2 7.2M8.6 1.4l-7.2 7.2" />
        </svg>
      </button>
    </div>
  );
}
