pub mod audio;
pub mod commands;
pub mod config;
pub mod desktop_integration;
pub mod diagnostics;
pub mod engines;
pub mod history;
pub mod hotkey;
pub mod input;
pub mod permissions;
pub mod polish;
pub mod sound;
pub mod tray;
pub mod window_info;

use log::{error, info};
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use serde::Serialize;
use std::sync::Arc;
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_autostart::MacosLauncher;

use audio::AudioRecorder;
use config::Config;
use engines::Engine;
use hotkey::HotkeyManager;

/// Global application state
/// Cached app info (name and icon base64)
#[derive(Debug, Clone, Default)]
pub struct CachedAppInfo {
    pub name: String,
    pub icon: Option<String>,
    pub window_id: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct UiSnapshot {
    pub phase: String,
    pub audio_level: f32,
    pub partial_result: String,
    pub final_result: String,
    pub error_message: String,
    pub app_name: String,
    pub app_icon: Option<String>,
}

impl Default for UiSnapshot {
    fn default() -> Self {
        Self {
            phase: "idle".to_string(),
            audio_level: 0.0,
            partial_result: String::new(),
            final_result: String::new(),
            error_message: String::new(),
            app_name: String::new(),
            app_icon: None,
        }
    }
}

pub struct AppState {
    pub config: RwLock<Config>,
    pub recorder: RwLock<Option<AudioRecorder>>,
    pub engine: RwLock<Option<Box<dyn Engine + Send + Sync>>>,
    pub hotkey_manager: RwLock<Option<HotkeyManager>>,
    pub last_focused_app: RwLock<CachedAppInfo>,
    pub ui: RwLock<UiSnapshot>,
    pub realtime_session: RwLock<Option<engines::VolcRealtimeSession>>,
}

impl AppState {
    pub fn new() -> Self {
        let config = Config::load().unwrap_or_default();
        Self {
            config: RwLock::new(config),
            recorder: RwLock::new(None),
            engine: RwLock::new(None),
            hotkey_manager: RwLock::new(None),
            last_focused_app: RwLock::new(CachedAppInfo::default()),
            ui: RwLock::new(UiSnapshot::default()),
            realtime_session: RwLock::new(None),
        }
    }
}

pub static APP_STATE: Lazy<Arc<AppState>> = Lazy::new(|| Arc::new(AppState::new()));

pub(crate) fn show_settings_window(app: &AppHandle) -> tauri::Result<()> {
    let window = if let Some(window) = app.get_webview_window("settings") {
        window
    } else {
        // Some Linux window managers destroy the native window before
        // CloseRequested can be cancelled. Recreate it so the tray action is
        // reliable even after the title-bar close button was used.
        WebviewWindowBuilder::new(
            app,
            "settings",
            WebviewUrl::App("index.html#settings".into()),
        )
        .title("Speaky Settings")
        .inner_size(900.0, 700.0)
        .min_inner_size(760.0, 600.0)
        .resizable(true)
        .center()
        .build()?
    };
    window.show()?;
    window.set_focus()?;
    Ok(())
}

pub(crate) fn show_diagnostics_window(app: &AppHandle) -> tauri::Result<()> {
    let window = if let Some(window) = app.get_webview_window("diagnostics") {
        window
    } else {
        WebviewWindowBuilder::new(
            app,
            "diagnostics",
            WebviewUrl::App("index.html#diagnostics".into()),
        )
        .title("Speaky Diagnostics")
        .inner_size(680.0, 620.0)
        .min_inner_size(560.0, 480.0)
        .center()
        .build()?
    };
    window.show()?;
    window.set_focus()?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    if let Err(error) = diagnostics::init_logging() {
        eprintln!("Failed to initialize logging: {}", error);
    }

    info!("Starting Speaky...");

    tauri::Builder::default()
        // Note: Using rdev for keyboard listening instead of global-shortcut plugin
        // to support modifier keys (ctrl, alt, shift) as hotkeys
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        // Prevent auto-start and a manual launch from creating duplicate
        // tray icons and competing settings windows.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
            }
        }))
        .setup(|app| {
            info!("Setting up application...");

            // The floating status window must never steal focus from the
            // application that should receive the recognized text.
            if let Some(window) = app.get_webview_window("main") {
                window.set_focusable(false)?;
            }

            // Initialize audio recorder
            {
                let config = APP_STATE.config.read();
                let device_index = config.core.asr.audio_device;
                let device_name = config.core.asr.audio_device_name.as_deref();
                let gain = config.core.asr.audio_gain;
                match AudioRecorder::new_with_name(device_index, device_name, gain) {
                    Ok(recorder) => {
                        *APP_STATE.recorder.write() = Some(recorder);
                        info!("Audio recorder initialized successfully");
                    }
                    Err(e) => {
                        error!("Failed to initialize audio recorder: {}", e);
                        *APP_STATE.recorder.write() = None;
                    }
                }
            }

            // Initialize engine based on config
            {
                let config = APP_STATE.config.read();
                let engine = engines::create_engine(&config);
                *APP_STATE.engine.write() = engine;
            }

            tray::install(app.handle())?;
            if let Err(error) = desktop_integration::install() {
                error!("Failed to install desktop integration: {}", error);
            }

            // Create the virtual paste keyboard before rdev begins watching
            // for hot-plugged input devices. This prevents a udev ACL race
            // from terminating the hotkey listener after the first paste.
            #[cfg(target_os = "linux")]
            if let Err(error) = input::prepare_paste_input() {
                error!("Failed to prepare Wayland paste input: {}", error);
            }

            // Register hotkeys
            let app_handle = app.handle().clone();
            hotkey::register_hotkeys(app_handle)?;

            // Useful for desktop launchers and automated smoke checks without
            // changing the normal hidden-at-start behavior.
            if std::env::var_os("SPEAKY_OPEN_SETTINGS").is_some() {
                show_settings_window(app.handle())?;
            }
            if std::env::var_os("SPEAKY_OPEN_DIAGNOSTICS").is_some() {
                show_diagnostics_window(app.handle())?;
            }

            info!("Application setup complete");
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the settings window used to destroy its webview, so the
            // tray menu could no longer open it a second time. Treat the title
            // bar close button like Cancel and keep the window reusable.
            if window.label() == "settings" || window.label() == "diagnostics" {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    if window.label() == "settings" {
                        if let Some(ref manager) = *APP_STATE.hotkey_manager.read() {
                            manager.cancel_capture();
                        }
                    }
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_config,
            commands::save_config,
            commands::start_recording,
            commands::stop_recording,
            commands::get_audio_devices,
            commands::set_hotkey,
            commands::start_hotkey_capture,
            commands::cancel_hotkey_capture,
            commands::show_window,
            commands::hide_window,
            commands::paste_text,
            commands::get_focused_app_info,
            commands::get_ui_state,
            commands::get_history,
            commands::clear_history,
            commands::get_diagnostics,
            commands::read_diagnostic_log,
            commands::clear_diagnostic_log,
            commands::export_diagnostic_log,
            commands::copy_text,
            commands::open_permission_settings,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| {
            if let RunEvent::ExitRequested { api: _, .. } = event {
                // Clean up resources before exit
                info!("Application exiting...");
            }
        });
}
