use log::{info, warn};
use serde::Serialize;
use tauri::{command, AppHandle, Manager};

use crate::audio::AudioRecorder;
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
pub fn save_config(config: Config) -> Result<(), String> {
    info!("Saving configuration");

    // Normalize stale device indices before persisting. A native <select>
    // can briefly produce an out-of-range value while its options reload.
    let mut config = config;
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
    if let Some(index) = config.core.asr.audio_device {
        let devices = AudioRecorder::get_devices();
        if !devices.iter().any(|(candidate, _)| *candidate == index) {
            warn!(
                "Ignoring unavailable audio device index {}; keeping the current selection",
                index
            );
            config.core.asr.audio_device = APP_STATE.config.read().core.asr.audio_device;
        }
    }

    // Build the recorder first. Never replace a working recorder with an
    // unusable one if settings contain a stale device selection.
    let new_recorder = AudioRecorder::new(config.core.asr.audio_device, config.core.asr.audio_gain)
        .map_err(|e| format!("Failed to recreate recorder: {}", e))?;

    config.save().map_err(|e| e.to_string())?;

    // Update in-memory config
    *APP_STATE.config.write() = config.clone();

    // Recreate engine with new config
    let engine = engines::create_engine(&config);
    *APP_STATE.engine.write() = engine;

    // Update recorder settings
    *APP_STATE.recorder.write() = Some(new_recorder);

    info!("Configuration saved successfully");
    Ok(())
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
}

#[command]
pub fn get_audio_devices() -> Vec<AudioDeviceInfo> {
    AudioRecorder::get_devices()
        .into_iter()
        .map(|(index, name)| AudioDeviceInfo { index, name })
        .collect()
}

/// Update hotkey settings
#[command]
pub fn set_hotkey(_app: AppHandle, hotkey: String, hold_time: f64) -> Result<(), String> {
    info!("Setting hotkey: {} with hold time: {}", hotkey, hold_time);

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

/// Show main window
#[command]
pub fn show_window(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Hide main window
#[command]
pub fn hide_window(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        window.hide().map_err(|e| e.to_string())?;
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
