mod keychain;
mod sidecar;
mod terminal;

use keychain::{delete_api_key, has_api_key, save_api_key};
use sidecar::{SidecarState, get_backend_port, shutdown as sidecar_shutdown, start_backend};
use terminal::{
    TerminalState, kill_shell, resize_shell, shutdown as terminal_shutdown, spawn_shell,
    write_to_shell,
};
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_log::Builder::default()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(SidecarState::new())
        .manage(TerminalState::new())
        .invoke_handler(tauri::generate_handler![
            has_api_key,
            save_api_key,
            delete_api_key,
            start_backend,
            get_backend_port,
            spawn_shell,
            write_to_shell,
            resize_shell,
            kill_shell,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let sidecar_state = window.state::<SidecarState>();
                sidecar_shutdown(&sidecar_state);
                let terminal_state = window.state::<TerminalState>();
                terminal_shutdown(&terminal_state);
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
