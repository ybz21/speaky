use log::{info, warn};
use serde::Serialize;
use tauri::{command, AppHandle, Manager};
use tauri_plugin_autostart::ManagerExt as AutostartExt;
use tauri_plugin_clipboard_manager::ClipboardExt;

use crate::audio::{detected_system_default_input_name, AudioRecorder};
use crate::config::Config;
use crate::engines;
use crate::hotkey;
use crate::input;
use crate::{UiSnapshot, APP_STATE};

/// Get current configuration
#[command]
pub fn get_config() -> Config {
    APP_STATE.config.read().clone()
}

/// Snapshot used by the floating window. Polling this lightweight state also
/// covers the first-show race where a hidden Linux webview has not registered
/// its event listeners yet.
#[command]
pub fn get_ui_state() -> UiSnapshot {
    APP_STATE.ui.read().clone()
}

/// Save configuration
#[command]
pub fn save_config(app: AppHandle, config: Config) -> Result<(), String> {
    info!("Saving configuration");

    // Normalize stale device indices before persisting. A native <select>
    // can briefly produce an out-of-range value while its options reload.
    let mut config = config;
    if !hotkey::is_supported_hotkey(&config.core.asr.hotkey) {
        return Err(format!("Unsupported hotkey: {}", config.core.asr.hotkey));
    }
    config.core.asr.language = "auto".to_string();
    config.appearance.ui_language = if config
        .appearance
        .ui_language
        .to_lowercase()
        .starts_with("en")
    {
        "en-US".to_string()
    } else {
        "zh-CN".to_string()
    };
    // Resolve the stable device name against the current enumeration. The
    // numeric index is only a transport detail and can change after USB or
    // PipeWire reconnects.
    let devices = AudioRecorder::get_devices();
    if let Some(name) = config.core.asr.audio_device_name.as_deref() {
        if let Some((index, _)) = devices.iter().find(|(_, candidate)| candidate == name) {
            config.core.asr.audio_device = Some(*index);
        } else {
            warn!(
                "Configured audio device '{}' is unavailable; falling back to automatic device selection",
                name
            );
            config.core.asr.audio_device = None;
        }
    } else if let Some(index) = config.core.asr.audio_device {
        if !devices.iter().any(|(candidate, _)| *candidate == index) {
            warn!(
                "Ignoring unavailable audio device index {}; falling back to automatic device selection",
                index
            );
            config.core.asr.audio_device = None;
        }
    }
    config.validate().map_err(|error| error.to_string())?;

    // Build the recorder first. Never replace a working recorder with an
    // unusable one if settings contain a stale device selection.
    let new_recorder = AudioRecorder::new_with_name(
        config.core.asr.audio_device,
        config.core.asr.audio_device_name.as_deref(),
        config.core.asr.audio_gain,
    )
    .map_err(|e| format!("Failed to recreate recorder: {}", e))?;

    config.save().map_err(|e| e.to_string())?;

    // Update in-memory config
    *APP_STATE.config.write() = config.clone();

    // Apply trigger changes immediately; settings no longer require a restart.
    if let Some(ref manager) = *APP_STATE.hotkey_manager.read() {
        manager.update_hotkey(&config.core.asr.hotkey);
        manager.update_hold_time(config.core.asr.hotkey_hold_time);
    }

    // Recreate engine with new config
    let engine = engines::create_engine(&config);
    *APP_STATE.engine.write() = engine;

    // Update recorder settings
    *APP_STATE.recorder.write() = Some(new_recorder);

    let autostart_result = if config.desktop.auto_start {
        app.autolaunch().enable()
    } else {
        app.autolaunch().disable()
    };
    if let Err(error) = autostart_result {
        warn!("Failed to synchronize autostart: {}", error);
    }
    if let Err(error) = crate::desktop_integration::install() {
        warn!("Failed to refresh desktop integration: {}", error);
    }
    crate::tray::refresh(&app);

    info!("Configuration saved successfully");
    Ok(())
}

#[command]
pub fn get_history() -> Vec<crate::history::HistoryItem> {
    crate::history::recent(50)
}

#[command]
pub fn clear_history(app: AppHandle) {
    crate::history::clear();
    crate::tray::refresh(&app);
}

#[command]
pub fn get_diagnostics() -> crate::diagnostics::DiagnosticSnapshot {
    crate::diagnostics::snapshot()
}

#[command]
pub fn read_diagnostic_log() -> Result<String, String> {
    crate::diagnostics::read_log()
}

#[command]
pub fn clear_diagnostic_log() -> Result<(), String> {
    crate::diagnostics::clear_log()
}

#[command]
pub fn export_diagnostic_log() -> Result<String, String> {
    crate::diagnostics::export_log()
}

#[command]
pub fn copy_text(app: AppHandle, text: String) -> Result<(), String> {
    app.clipboard()
        .write_text(text)
        .map_err(|error| error.to_string())
}

#[command]
pub fn open_permission_settings() -> Result<(), String> {
    crate::permissions::open_settings()
}

/// Start audio recording
#[command]
pub fn start_recording() -> Result<(), String> {
    info!("Starting recording via command");

    if let Some(ref mut recorder) = *APP_STATE.recorder.write() {
        recorder.start()
    } else {
        Err("Recorder not initialized".to_string())
    }
}

/// Stop audio recording and return audio data
#[command]
pub fn stop_recording(app: AppHandle) -> Result<(), String> {
    info!("Stopping recording via command");

    if let Some(ref mut recorder) = *APP_STATE.recorder.write() {
        let audio_data = recorder.stop();
        hotkey::recognize_and_deliver(app, audio_data);
        Ok(())
    } else {
        Err("Recorder not initialized".to_string())
    }
}

/// Get list of audio input devices
#[derive(Serialize)]
pub struct AudioDeviceInfo {
    index: u32,
    name: String,
    is_default: bool,
}

#[command]
pub fn get_audio_devices() -> Vec<AudioDeviceInfo> {
    let system_default = detected_system_default_input_name();
    AudioRecorder::get_devices()
        .into_iter()
        .map(|(index, name)| {
            let is_default = system_default.as_deref().is_some_and(|detected| {
                let name = name.to_lowercase();
                let detected = detected.to_lowercase();
                name == detected || name.contains(&detected) || detected.contains(&name)
            });
            AudioDeviceInfo {
                index,
                name,
                is_default,
            }
        })
        .collect()
}

/// Update hotkey settings
#[command]
pub fn set_hotkey(_app: AppHandle, hotkey: String, hold_time: f64) -> Result<(), String> {
    info!("Setting hotkey: {} with hold time: {}", hotkey, hold_time);

    if !hotkey::is_supported_hotkey(&hotkey) {
        return Err(format!("Unsupported hotkey: {}", hotkey));
    }
    if hold_time <= 0.0 {
        return Err("Hold time must be positive".to_string());
    }

    // Update config and hotkey manager atomically
    {
        let mut config = APP_STATE.config.write();
        config.core.asr.hotkey = hotkey.clone();
        config.core.asr.hotkey_hold_time = hold_time;

        // Save config - ignore error if file write fails (hotkey still works in memory)
        let _ = config.save();

        // Update hotkey manager if available
        if let Some(ref manager) = *APP_STATE.hotkey_manager.read() {
            manager.update_hotkey(&hotkey);
            manager.update_hold_time(hold_time);
        }
    }

    // Note: Full hotkey re-registration would require unregistering old and registering new
    // This simplified implementation updates the manager settings

    Ok(())
}

#[command]
pub fn start_hotkey_capture() -> Result<(), String> {
    let managers = APP_STATE.hotkey_manager.read();
    let manager = managers
        .as_ref()
        .ok_or_else(|| "Keyboard listener is not ready".to_string())?;
    manager.begin_capture();
    Ok(())
}

#[command]
pub fn cancel_hotkey_capture() {
    if let Some(ref manager) = *APP_STATE.hotkey_manager.read() {
        manager.cancel_capture();
    }
}

/// Show main window
#[command]
pub fn show_window(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        // This command is also used by the development UI. Showing the
        // status overlay must not move focus away from Chrome, ChatGPT, or
        // whichever editor the user was typing in.
        window.set_focusable(false).map_err(|e| e.to_string())?;
        window.show().map_err(|e| e.to_string())?;
        window.set_focusable(false).map_err(|e| e.to_string())?;
        window
            .set_ignore_cursor_events(true)
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Hide main window
#[command]
pub fn hide_window(app: AppHandle) -> Result<(), String> {
    // Conceal the mapped overlay through the UI state. Keeping the native
    // surface mapped avoids a Wayland focus jump on the next recording.
    {
        let mut ui = APP_STATE.ui.write();
        ui.phase = "idle".to_string();
        ui.audio_level = 0.0;
        ui.partial_result.clear();
        ui.final_result.clear();
        ui.error_message.clear();
    }
    if let Some(window) = app.get_webview_window("main") {
        // Keep the native surface mapped. Hiding and showing a Wayland
        // window can activate it and steal the user's text cursor.
        window.set_focusable(false).map_err(|e| e.to_string())?;
        window
            .set_ignore_cursor_events(true)
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Paste text to current application
#[command]
pub fn paste_text(app: AppHandle, text: String) -> Result<(), String> {
    info!("Pasting text via command");
    input::paste_text(&app, &text).map_err(|e| e.to_string())
}

/// Get last focused app info (cached from before window was shown)
#[command]
pub fn get_focused_app_info() -> Result<serde_json::Value, String> {
    let app_info = APP_STATE.last_focused_app.read();

    info!(
        "get_focused_app_info: {} (icon: {})",
        app_info.name,
        app_info.icon.is_some()
    );

    Ok(serde_json::json!({
        "name": if app_info.name.is_empty() { "Unknown".to_string() } else { app_info.name.clone() },
        "icon": app_info.icon.clone()
    }))
}
