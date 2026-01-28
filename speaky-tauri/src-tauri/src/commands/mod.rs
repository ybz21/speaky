use log::info;
use tauri::{command, AppHandle, Manager};

use crate::audio::AudioRecorder;
use crate::config::Config;
use crate::engines;
use crate::input;
use crate::APP_STATE;

/// Get current configuration
#[command]
pub fn get_config() -> Config {
    APP_STATE.config.read().clone()
}

/// Save configuration
#[command]
pub fn save_config(config: Config) -> Result<(), String> {
    info!("Saving configuration");

    // Save to file
    config.save().map_err(|e| e.to_string())?;

    // Update in-memory config
    *APP_STATE.config.write() = config.clone();

    // Recreate engine with new config
    let engine = engines::create_engine(&config);
    *APP_STATE.engine.write() = engine;

    // Update recorder settings
    if let Some(ref mut recorder) = *APP_STATE.recorder.write() {
        // Recreate recorder with new settings
        let new_recorder = AudioRecorder::new(
            config.core.asr.audio_device,
            config.core.asr.audio_gain,
        );
        *recorder = new_recorder;
    }

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
pub fn stop_recording() -> Result<Vec<u8>, String> {
    info!("Stopping recording via command");

    if let Some(ref mut recorder) = *APP_STATE.recorder.write() {
        Ok(recorder.stop())
    } else {
        Err("Recorder not initialized".to_string())
    }
}

/// Get list of audio input devices
#[command]
pub fn get_audio_devices() -> Vec<(u32, String)> {
    AudioRecorder::get_devices()
}

/// Update hotkey settings
#[command]
pub fn set_hotkey(app: AppHandle, hotkey: String, hold_time: f64) -> Result<(), String> {
    info!("Setting hotkey: {} with hold time: {}", hotkey, hold_time);

    // Update config
    {
        let mut config = APP_STATE.config.write();
        config.core.asr.hotkey = hotkey.clone();
        config.core.asr.hotkey_hold_time = hold_time;
        config.save().map_err(|e| e.to_string())?;
    }

    // Update hotkey manager
    if let Some(ref mut manager) = *APP_STATE.hotkey_manager.write() {
        manager.update_hotkey(&hotkey);
        manager.update_hold_time(hold_time);
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
    input::paste_text(&app, &text)
}
