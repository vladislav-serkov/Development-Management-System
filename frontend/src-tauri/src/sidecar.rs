use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;

use tauri::{AppHandle, Emitter, Manager};

use crate::keychain;

#[derive(serde::Serialize, Clone)]
pub struct BackendReadyPayload {
    pub port: u16,
}

pub struct SidecarState {
    pub child: Mutex<Option<Child>>,
    pub port: Mutex<Option<u16>>,
    pub start_lock: Mutex<()>,
}

impl SidecarState {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            port: Mutex::new(None),
            start_lock: Mutex::new(()),
        }
    }
}

fn find_project_root() -> Option<PathBuf> {
    let mut dir = std::env::current_dir().ok()?;
    loop {
        if dir.join("pyproject.toml").exists() {
            return Some(dir);
        }
        if !dir.pop() {
            return None;
        }
    }
}

fn find_python(project_root: &Path) -> PathBuf {
    if let Ok(p) = std::env::var("EXTRACT_AGENT_PYTHON") {
        return PathBuf::from(p);
    }
    let venv = project_root.join(".venv/bin/python");
    if venv.exists() {
        return venv;
    }
    PathBuf::from("python3")
}

struct SpawnCommand {
    program: PathBuf,
    args: Vec<String>,
    cwd: Option<PathBuf>,
}

fn build_dev_command() -> Result<SpawnCommand, String> {
    let project_root = find_project_root()
        .ok_or_else(|| "pyproject.toml not found — cannot locate project root".to_string())?;
    let python = find_python(&project_root);
    Ok(SpawnCommand {
        program: python,
        args: vec!["-m".into(), "app.sidecar".into()],
        cwd: Some(project_root),
    })
}

fn build_release_command(app: &AppHandle) -> Result<SpawnCommand, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("cannot resolve resource_dir: {e}"))?;
    let binary = resource_dir
        .join("extract-agent-backend")
        .join("extract-agent-backend");
    if !binary.exists() {
        return Err(format!(
            "bundled sidecar not found at {}",
            binary.display()
        ));
    }
    Ok(SpawnCommand {
        program: binary,
        args: vec![],
        cwd: None,
    })
}

fn build_command(app: &AppHandle) -> Result<SpawnCommand, String> {
    if cfg!(debug_assertions) {
        build_dev_command()
    } else {
        build_release_command(app)
    }
}

fn spawn(app: &AppHandle) -> Result<(), String> {
    let spec = build_command(app)?;

    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("cannot resolve app_data_dir: {e}"))?
        .join("data")
        .join("projects");
    std::fs::create_dir_all(&data_dir)
        .map_err(|e| format!("cannot create DATA_DIR {}: {e}", data_dir.display()))?;

    log::info!(
        "Starting sidecar: {} {} (cwd={:?}, DATA_DIR={})",
        spec.program.display(),
        spec.args.join(" "),
        spec.cwd.as_ref().map(|p| p.display().to_string()),
        data_dir.display()
    );

    let mut cmd = Command::new(&spec.program);
    for arg in &spec.args {
        cmd.arg(arg);
    }
    if let Some(cwd) = &spec.cwd {
        cmd.current_dir(cwd);
    }
    cmd.env("DATA_DIR", &data_dir)
        .env("PYTHONUNBUFFERED", "1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(key) = keychain::read_api_key() {
        cmd.env("ANTHROPIC_API_KEY", key);
    }

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("failed to spawn sidecar: {e}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "sidecar has no stdout".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "sidecar has no stderr".to_string())?;

    let state = app.state::<SidecarState>();
    *state.child.lock().unwrap() = Some(child);
    *state.port.lock().unwrap() = None;

    let app_for_stdout = app.clone();
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines().map_while(Result::ok) {
            if let Some(port_str) = line.strip_prefix("EXTRACT_AGENT_PORT=") {
                if let Ok(port) = port_str.trim().parse::<u16>() {
                    let state = app_for_stdout.state::<SidecarState>();
                    *state.port.lock().unwrap() = Some(port);
                    let _ = app_for_stdout.emit("backend-ready", BackendReadyPayload { port });
                    log::info!("sidecar ready on port {port}");
                    continue;
                }
            }
            log::info!("[sidecar] {line}");
        }
        log::warn!("sidecar stdout closed");
    });

    thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().map_while(Result::ok) {
            log::info!("[sidecar] {line}");
        }
    });

    Ok(())
}

pub fn shutdown(state: &SidecarState) {
    if let Some(mut child) = state.child.lock().unwrap().take() {
        log::info!("Shutting down sidecar...");
        let _ = child.kill();
        let _ = child.wait();
    }
    *state.port.lock().unwrap() = None;
}

#[tauri::command]
pub fn start_backend(app: AppHandle, state: tauri::State<SidecarState>) -> Result<(), String> {
    let _serialized = state.start_lock.lock().unwrap();
    if state.child.lock().unwrap().is_some() {
        log::info!("Backend already running, start_backend is a no-op");
        return Ok(());
    }
    spawn(&app)
}

#[tauri::command]
pub fn get_backend_port(state: tauri::State<SidecarState>) -> Option<u16> {
    *state.port.lock().unwrap()
}
