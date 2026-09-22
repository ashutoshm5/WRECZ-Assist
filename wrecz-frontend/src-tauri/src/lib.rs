//! WRECZ desktop shell.
//!
//! The window is only half the job. The shell also owns the Python bridge:
//! it starts uvicorn on launch and kills it on exit. An orphaned bridge keeps
//! the audio device, the security tray icon and port 8765, which makes the
//! next launch fail in a confusing way.

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::{Manager, RunEvent};

const BRIDGE_HOST: &str = "127.0.0.1";
const BRIDGE_PORT: &str = "8765";
const BRIDGE_PORT_NUM: u16 = 8765;

/// The Python bridge, owned by the shell for the lifetime of the window.
struct Bridge(Mutex<Option<Child>>);

/// Dev layout: <repo>/wrecz-frontend/src-tauri -> <repo>/wrecz
fn bridge_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("wrecz")
}

/// A bridge already on the port means a previous WRECZ is still running.
/// Left unchecked the new window silently attaches to it, which is how you
/// end up talking to an hours-old process that predates your code changes.
fn port_in_use() -> bool {
    TcpStream::connect((BRIDGE_HOST, BRIDGE_PORT_NUM)).is_ok()
}

fn spawn_bridge() -> Option<Child> {
    if port_in_use() {
        eprintln!(
            "[WRECZ] Port {BRIDGE_PORT} is already in use.
             [WRECZ] Another WRECZ bridge is running and this window will
             [WRECZ] attach to IT, not to a fresh one - so recent changes to
             [WRECZ] the Python code will NOT be loaded.
             [WRECZ] Close the other WRECZ (or kill that process) and relaunch."
        );
        return None;
    }

    let dir = bridge_dir();
    let python = dir.join(".venv").join("Scripts").join("python.exe");

    if !python.exists() {
        eprintln!(
            "[WRECZ] No Python venv at {}.\n\
             [WRECZ] The window will still open; start the bridge yourself with\n\
             [WRECZ]   python run_all.py\n\
             [WRECZ] or correct the path in src-tauri/src/lib.rs.",
            python.display()
        );
        return None;
    }

    let mut command = Command::new(&python);

    command
        .args([
            "-m",
            "uvicorn",
            "api_server:app",
            "--host",
            BRIDGE_HOST,
            "--port",
            BRIDGE_PORT,
            "--log-level",
            "info",
        ])
        .current_dir(&dir)
        // Inherit so bridge logs land in the terminal running `tauri dev`.
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());

    // Without this the child briefly flashes its own console window.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    match command.spawn() {
        Ok(child) => {
            println!(
                "[WRECZ] Bridge starting on {BRIDGE_HOST}:{BRIDGE_PORT} (pid {}).",
                child.id()
            );
            println!("[WRECZ] First launch takes ~25s while torch and Kokoro load.");
            Some(child)
        }
        Err(error) => {
            eprintln!("[WRECZ] Could not start the bridge: {error}");
            None
        }
    }
}

fn stop_bridge(child: &mut Child) {
    // uvicorn without --reload is a single process, so this is enough. The
    // security tray lives on a daemon thread inside it and goes with it.
    let _ = child.kill();
    let _ = child.wait();
    println!("[WRECZ] Bridge stopped.");
}

pub fn run() {
    tauri::Builder::default()
        .manage(Bridge(Mutex::new(None)))
        .setup(|app| {
            let bridge = app.state::<Bridge>();
            *bridge.0.lock().unwrap() = spawn_bridge();
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to start the WRECZ desktop shell")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(mut child) = app.state::<Bridge>().0.lock().unwrap().take() {
                    stop_bridge(&mut child);
                }
            }
        });
}
