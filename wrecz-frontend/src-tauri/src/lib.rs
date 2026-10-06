//! WRECZ desktop shell.
//!
//! The window manages both services:
//! 1. The Vite frontend dev server (port 8443) - initialized first with a 2-second readiness delay.
//! 2. The Python FastAPI bridge (port 8765) in the background.
//! The desktop window is displayed only after the frontend server is ready to prevent error flashes.
//! Both services are cleanly terminated when the window is closed.

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent};

const BRIDGE_HOST: &str = "127.0.0.1";
const BRIDGE_PORT: &str = "8765";
const BRIDGE_PORT_NUM: u16 = 8765;

const FRONTEND_HOST: &str = "127.0.0.1";
const FRONTEND_PORT: &str = "8443";
const FRONTEND_PORT_NUM: u16 = 8443;

/// Manages the Python bridge and Vite frontend child processes
struct Services {
    bridge: Mutex<Option<Child>>,
    frontend: Mutex<Option<Child>>,
}

/// Finds the Python bridge directory dynamically
fn bridge_dir() -> PathBuf {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            let c1 = parent.join("..").join("wrecz");
            if c1.join(".venv").exists() {
                return c1;
            }
            let c2 = parent.join("wrecz");
            if c2.join(".venv").exists() {
                return c2;
            }
            let c3 = parent.join("..").join("..").join("..").join("wrecz");
            if c3.join(".venv").exists() {
                return c3;
            }
        }
    }
    let standard = PathBuf::from(r"C:\Wrecz\wrecz");
    if standard.join(".venv").exists() {
        return standard;
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("wrecz")
}

/// Finds the frontend directory dynamically
fn frontend_dir() -> PathBuf {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            if parent.join("package.json").exists() {
                return parent.to_path_buf();
            }
            let c1 = parent.join("wrecz-frontend");
            if c1.join("package.json").exists() {
                return c1;
            }
            let c2 = parent.join("..").join("wrecz-frontend");
            if c2.join("package.json").exists() {
                return c2;
            }
            let c3 = parent.join("..").join("..");
            if c3.join("package.json").exists() {
                return c3;
            }
        }
    }
    let standard = PathBuf::from(r"C:\Wrecz\wrecz-frontend");
    if standard.join("package.json").exists() {
        return standard;
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn port_in_use(host: &str, port: u16) -> bool {
    TcpStream::connect((host, port)).is_ok()
}

fn spawn_frontend() -> Option<Child> {
    if port_in_use(FRONTEND_HOST, FRONTEND_PORT_NUM) {
        println!("[WRECZ] Frontend port {FRONTEND_PORT} already in use; attaching to existing server.");
        return None;
    }

    let dir = frontend_dir();
    let npm_cmd = if cfg!(windows) { "npm.cmd" } else { "npm" };
    let mut command = Command::new(npm_cmd);
    command
        .args(["run", "dev", "--", "--port", FRONTEND_PORT, "--host", FRONTEND_HOST])
        .current_dir(&dir)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    match command.spawn() {
        Ok(child) => {
            println!(
                "[WRECZ] Frontend Vite server starting on {FRONTEND_HOST}:{FRONTEND_PORT} (pid {}).",
                child.id()
            );
            Some(child)
        }
        Err(error) => {
            eprintln!("[WRECZ] Could not start frontend dev server: {error}");
            None
        }
    }
}

fn spawn_bridge() -> Option<Child> {
    if port_in_use(BRIDGE_HOST, BRIDGE_PORT_NUM) {
        println!(
            "[WRECZ] Bridge port {BRIDGE_PORT} is already in use; attaching to existing instance."
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
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());

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

fn stop_child(child: &mut Child) {
    #[cfg(windows)]
    {
        let pid = child.id();
        let _ = Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .output();
    }
    let _ = child.kill();
    let _ = child.wait();
}

pub fn run() {
    // 1. Start the frontend Vite server first
    let frontend_child = spawn_frontend();

    // 2. Start the Python bridge in parallel
    let bridge_child = spawn_bridge();

    // 3. Wait for the frontend server on port 8443 to be responsive
    println!("[WRECZ] Waiting for frontend server on {FRONTEND_HOST}:{FRONTEND_PORT}...");
    let start_wait = Instant::now();
    while start_wait.elapsed() < Duration::from_secs(6) {
        if port_in_use(FRONTEND_HOST, FRONTEND_PORT_NUM) {
            println!("[WRECZ] Frontend port {FRONTEND_PORT} is active.");
            break;
        }
        std::thread::sleep(Duration::from_millis(150));
    }

    // 4. Ensure Vite's HTTP server is fully warm and ready (~2-second total delay)
    std::thread::sleep(Duration::from_millis(1800));

    // 5. Build and launch Tauri window
    tauri::Builder::default()
        .manage(Services {
            bridge: Mutex::new(bridge_child),
            frontend: Mutex::new(frontend_child),
        })
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let icon_bytes = include_bytes!("../icons/128x128.png");
                if let Ok(icon) = tauri::image::Image::from_bytes(icon_bytes) {
                    let _ = window.set_icon(icon);
                }

                // Show the window now that the frontend server is verified active and responding
                let _ = window.show();
                let _ = window.set_focus();
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to start the WRECZ desktop shell")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                let services = app.state::<Services>();
                let maybe_bridge = services.bridge.lock().unwrap().take();
                if let Some(mut child) = maybe_bridge {
                    stop_child(&mut child);
                }
                let maybe_frontend = services.frontend.lock().unwrap().take();
                if let Some(mut child) = maybe_frontend {
                    stop_child(&mut child);
                }
            }
        });
}
