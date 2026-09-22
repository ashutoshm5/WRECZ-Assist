# WRECZ desktop shell (Tauri 2)

Runs WRECZ in a native window instead of a browser tab. This is the dev
setup: it runs from source and does not bundle Python or produce an installer.

## Run

```
npm run desktop
```

That is the whole thing. It:

1. starts Vite on `127.0.0.1:8443` (`beforeDevCommand`),
2. compiles and opens the native window,
3. starts the Python bridge on `127.0.0.1:8765` as a child of the shell,
4. kills the bridge again when you close the window.

First launch still takes ~25s before WRECZ answers, while torch and Kokoro
load. The window opens immediately and shows "Waiting for WRECZ..." until the
bridge is up; the frontend reconnects on its own.

Ollama must be running separately, as always.

The browser path still works unchanged: `python run_all.py` in the backend
repo, then open `http://127.0.0.1:8443`.

## Prerequisites

- **WebView2** - ships with Windows 11.
- **MSVC** - Visual Studio Build Tools with the C++ workload. `cl.exe` does
  not need to be on PATH; Rust finds it.
- **Rust** - `winget install --id Rustlang.Rustup -e`, then
  `rustup default stable-x86_64-pc-windows-msvc`.

Check all three with `npx tauri info`.

## Layout

```
src-tauri/
  tauri.conf.json      window, CSP, dev server wiring
  Cargo.toml
  build.rs
  src/main.rs          entry point
  src/lib.rs           window + Python bridge lifecycle
  capabilities/        window permissions granted to the frontend
  icons/               generated from app-icon.png
```

## Things worth knowing

**The shell owns the bridge.** `src/lib.rs` starts uvicorn on launch and kills
it on exit. An orphaned bridge keeps the audio device, the security tray icon
and port 8765, and the next launch then fails confusingly. If the venv is
missing the window still opens and says so, so you can start the bridge
yourself.

**One tray icon, not two.** WRECZ's `SecurityTray` is the internet kill
switch, so the shell deliberately does not add a tray icon of its own. The
tray lives on a daemon thread inside the bridge process and goes away with it.

**The window is frameless.** The design has no title bar, so `decorations` is
off, the header is the drag handle (`data-tauri-drag-region`) and
`WindowControls.tsx` supplies minimise / maximise / close in the top-right.
Those controls render nothing in a browser tab.

**Origins.** On Windows the shell serves the app from `http://tauri.localhost`,
not `tauri://localhost` - both are in the bridge's CORS allow list, along with
the Vite origin.

**CSP.** Tauri injects a Content-Security-Policy, and `connect-src` must name
the bridge explicitly or the WebSocket fails silently. `tauri.conf.json` has
two: `csp` for production and `devCsp`, which additionally allows the Vite
dev server and its HMR socket.

**Icons** are generated from `src-tauri/icon.svg` - the black tile with the
outlined triangle, the same mark as the send button. The Tauri CLI rasterises
SVG directly. After changing it, run `npx tauri icon src-tauri/icon.svg` and
rebuild: icons are embedded into the binary at compile time.

## Not done yet

- **Single instance.** Two windows means two bridges fighting over port 8765
  and the audio device. `tauri-plugin-single-instance` is the fix.
- **Packaging.** `npm run desktop:build` produces an installer for the *shell*
  only - it does not bundle Python, so the installed app still expects the
  repo and its venv on disk. Real packaging has to solve the 1 GB runtime
  (501 MB of it torch) and cannot bundle Ollama at all.
