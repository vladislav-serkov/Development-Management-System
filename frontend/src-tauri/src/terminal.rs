use std::io::{Read, Write};
use std::sync::Mutex;
use std::thread;

use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use tauri::{AppHandle, Emitter};

pub struct TerminalState {
    master: Mutex<Option<Box<dyn MasterPty + Send>>>,
    writer: Mutex<Option<Box<dyn Write + Send>>>,
    child: Mutex<Option<Box<dyn Child + Send + Sync>>>,
}

impl TerminalState {
    pub fn new() -> Self {
        Self {
            master: Mutex::new(None),
            writer: Mutex::new(None),
            child: Mutex::new(None),
        }
    }
}

fn detect_shell() -> String {
    std::env::var("SHELL").unwrap_or_else(|_| "/bin/zsh".to_string())
}

#[tauri::command]
pub fn spawn_shell(
    app: AppHandle,
    state: tauri::State<TerminalState>,
    cols: u16,
    rows: u16,
) -> Result<(), String> {
    if state.child.lock().unwrap().is_some() {
        return Ok(());
    }

    let pty_system = native_pty_system();
    let pair = pty_system
        .openpty(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| format!("openpty failed: {e}"))?;

    let shell = detect_shell();
    let home = std::env::var("HOME").unwrap_or_else(|_| "/".to_string());

    let mut cmd = CommandBuilder::new(&shell);
    cmd.cwd(&home);
    cmd.env("TERM", "xterm-256color");

    let child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| format!("spawn_command failed: {e}"))?;
    drop(pair.slave);

    let reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| format!("clone_reader failed: {e}"))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|e| format!("take_writer failed: {e}"))?;

    *state.master.lock().unwrap() = Some(pair.master);
    *state.writer.lock().unwrap() = Some(writer);
    *state.child.lock().unwrap() = Some(child);

    log::info!("Spawned shell: {shell} (cwd={home}, {cols}x{rows})");

    let app_clone = app.clone();
    thread::spawn(move || {
        let mut reader = reader;
        let mut buf = [0u8; 4096];
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    let chunk = String::from_utf8_lossy(&buf[..n]).to_string();
                    if app_clone.emit("pty-output", chunk).is_err() {
                        break;
                    }
                }
                Err(e) => {
                    log::warn!("pty read error: {e}");
                    break;
                }
            }
        }
        log::info!("pty reader thread exited");
        let _ = app_clone.emit("pty-exit", ());
    });

    Ok(())
}

#[tauri::command]
pub fn write_to_shell(state: tauri::State<TerminalState>, data: String) -> Result<(), String> {
    let mut guard = state.writer.lock().unwrap();
    let writer = guard
        .as_mut()
        .ok_or_else(|| "shell not running".to_string())?;
    writer
        .write_all(data.as_bytes())
        .map_err(|e| format!("write failed: {e}"))?;
    writer.flush().map_err(|e| format!("flush failed: {e}"))?;
    Ok(())
}

#[tauri::command]
pub fn resize_shell(
    state: tauri::State<TerminalState>,
    cols: u16,
    rows: u16,
) -> Result<(), String> {
    let guard = state.master.lock().unwrap();
    let master = guard
        .as_ref()
        .ok_or_else(|| "shell not running".to_string())?;
    master
        .resize(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| format!("resize failed: {e}"))
}

#[tauri::command]
pub fn kill_shell(state: tauri::State<TerminalState>) {
    if let Some(mut child) = state.child.lock().unwrap().take() {
        log::info!("Killing shell...");
        let _ = child.kill();
        let _ = child.wait();
    }
    state.master.lock().unwrap().take();
    state.writer.lock().unwrap().take();
}

pub fn shutdown(state: &TerminalState) {
    if let Some(mut child) = state.child.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    state.master.lock().unwrap().take();
    state.writer.lock().unwrap().take();
}
