# WRECZ Frontend — UI implementation pass 1

This project is the first clean React implementation of the supplied WRECZ Figma Make UI.

## Implemented

- Main WRECZ desktop layout
- Source-matched header icons and wordmark
- Account dropdown
- Settings dropdown with functional switches
- Notifications dropdown matching the supplied empty state
- App List / ENV dropdown
- One-dropdown-at-a-time behavior
- Outside-click and Escape-to-close behavior
- Composer and triangle interaction
- Hover state for the black send pill
- No fake assistant response or fake notification data

## Deliberately not connected yet

- Python/FastAPI
- Ollama
- STT/microphone
- TTS
- WRECZ speaking visualizer
- Tauri 2

The submit action currently emits a browser `wrecz:message` event and clears the composer. That is the bridge point for the later FastAPI/WebSocket integration.

## Run

```bash
npm install
npm run dev
```

Then open the Vite development URL shown in the terminal.

## Build

```bash
npm run build
```

The development environment used to prepare this archive did not have network access to install npm packages, so the final Vite build was not executed here. The source has been checked structurally against the supplied project.
