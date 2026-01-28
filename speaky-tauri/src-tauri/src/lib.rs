pub mod audio;
pub mod commands;
pub mod config;
pub mod engines;
pub mod hotkey;
pub mod input;
pub mod window_info;

use log::info;
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use std::sync::Arc;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, RunEvent,
};

use audio::AudioRecorder;
use config::Config;
use engines::Engine;
use hotkey::HotkeyManager;

/// Global application state
pub struct AppState {
    pub config: RwLock<Config>,
    pub recorder: RwLock<Option<AudioRecorder>>,
    pub engine: RwLock<Option<Box<dyn Engine + Send + Sync>>>,
    pub hotkey_manager: RwLock<Option<HotkeyManager>>,
}

impl AppState {
    pub fn new() -> Self {
        let config = Config::load().unwrap_or_default();
        Self {
            config: RwLock::new(config),
            recorder: RwLock::new(None),
            engine: RwLock::new(None),
            hotkey_manager: RwLock::new(None),
        }
    }
}

pub static APP_STATE: Lazy<Arc<AppState>> = Lazy::new(|| Arc::new(AppState::new()));

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    info!("Starting Speaky...");

    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_clipboard_manager::init())
        .setup(|app| {
            info!("Setting up application...");

            // Initialize audio recorder
            {
                let config = APP_STATE.config.read();
                let device_index = config.core.asr.audio_device;
                let gain = config.core.asr.audio_gain;
                let recorder = AudioRecorder::new(device_index, gain);
                *APP_STATE.recorder.write() = Some(recorder);
            }

            // Initialize engine based on config
            {
                let config = APP_STATE.config.read();
                let engine = engines::create_engine(&config);
                *APP_STATE.engine.write() = engine;
            }

            // Create tray menu
            let settings_item = MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&settings_item, &quit_item])?;

            // Create tray icon
            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "settings" => {
                        if let Some(window) = app.get_webview_window("settings") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            // Register hotkeys
            let app_handle = app.handle().clone();
            hotkey::register_hotkeys(app_handle)?;

            info!("Application setup complete");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_config,
            commands::save_config,
            commands::start_recording,
            commands::stop_recording,
            commands::get_audio_devices,
            commands::set_hotkey,
            commands::show_window,
            commands::hide_window,
            commands::paste_text,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { api, .. } = event {
                // Clean up resources before exit
                info!("Application exiting...");
            }
        });
}
