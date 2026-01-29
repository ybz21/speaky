use base64::Engine as _;
use log::{error, info};
use parking_lot::Mutex;
use rdev::{listen, Event, EventType, Key};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};

use crate::APP_STATE;

/// Hotkey manager for handling press-and-hold detection
pub struct HotkeyManager {
    hotkey: String,
    hold_time: Duration,
    press_time: Arc<Mutex<Option<Instant>>>,
    is_recording: Arc<AtomicBool>,
    hold_triggered: Arc<AtomicBool>,
    app_handle: Arc<Mutex<Option<AppHandle>>>,
}

impl HotkeyManager {
    pub fn new(hotkey: &str, hold_time: f64) -> Self {
        Self {
            hotkey: hotkey.to_lowercase(),
            hold_time: Duration::from_secs_f64(hold_time),
            press_time: Arc::new(Mutex::new(None)),
            is_recording: Arc::new(AtomicBool::new(false)),
            hold_triggered: Arc::new(AtomicBool::new(false)),
            app_handle: Arc::new(Mutex::new(None)),
        }
    }

    pub fn set_app_handle(&self, app: AppHandle) {
        *self.app_handle.lock() = Some(app);
    }

    pub fn update_hotkey(&mut self, hotkey: &str) {
        self.hotkey = hotkey.to_lowercase();
    }

    pub fn update_hold_time(&mut self, hold_time: f64) {
        self.hold_time = Duration::from_secs_f64(hold_time);
    }

    pub fn get_hotkey(&self) -> &str {
        &self.hotkey
    }

    pub fn on_press(&self) {
        let app = match self.app_handle.lock().clone() {
            Some(app) => app,
            None => return,
        };

        let mut press_time = self.press_time.lock();
        if press_time.is_none() {
            *press_time = Some(Instant::now());
            info!("Hotkey {} pressed, waiting for hold...", self.hotkey);

            // Spawn a timer to check hold time
            let hold_time = self.hold_time;
            let press_time_arc = Arc::clone(&self.press_time);
            let is_recording = Arc::clone(&self.is_recording);
            let hold_triggered = Arc::clone(&self.hold_triggered);
            let app_handle = app.clone();

            std::thread::spawn(move || {
                std::thread::sleep(hold_time);

                // Check if still pressed
                if press_time_arc.lock().is_some() && !hold_triggered.load(Ordering::SeqCst) {
                    hold_triggered.store(true, Ordering::SeqCst);
                    info!("Hold time reached, starting recording");

                    // Start recording
                    is_recording.store(true, Ordering::SeqCst);

                    // Get focused window info and emit app-info event
                    if let Some(info) = crate::window_info::get_focused_window_info() {
                        // Convert icon to base64 data URL if it exists
                        let icon_data = info.icon_path.as_ref().and_then(|path| {
                            std::fs::read(path).ok().map(|data| {
                                let ext = std::path::Path::new(path)
                                    .extension()
                                    .and_then(|e| e.to_str())
                                    .unwrap_or("png");
                                let mime = match ext {
                                    "svg" => "image/svg+xml",
                                    "png" => "image/png",
                                    "jpg" | "jpeg" => "image/jpeg",
                                    _ => "image/png",
                                };
                                format!(
                                    "data:{};base64,{}",
                                    mime,
                                    base64::Engine::encode(
                                        &base64::engine::general_purpose::STANDARD,
                                        &data
                                    )
                                )
                            })
                        });

                        let _ = app_handle.emit(
                            "app-info",
                            serde_json::json!({
                                "name": info.app_name,
                                "icon": icon_data
                            }),
                        );
                        info!(
                            "Focused app: {} (icon: {})",
                            info.app_name,
                            icon_data.is_some()
                        );
                    }

                    // Emit recording state event
                    let _ = app_handle.emit(
                        "recording-state",
                        serde_json::json!({
                            "state": "started"
                        }),
                    );

                    // Show main window
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }

                    // Start audio recording
                    if let Some(ref mut recorder) = *APP_STATE.recorder.write() {
                        // Set up audio level callback
                        let app_for_level = app_handle.clone();
                        recorder.set_audio_level_callback(move |level| {
                            // Multiply by 3 to match Python implementation
                            let _ = app_for_level.emit(
                                "audio-level",
                                serde_json::json!({
                                    "level": level * 3.0
                                }),
                            );
                        });

                        if let Err(e) = recorder.start() {
                            error!("Failed to start recording: {}", e);
                            let _ = app_handle.emit(
                                "recognition-error",
                                serde_json::json!({
                                    "message": e
                                }),
                            );
                        }
                    }
                }
            });
        }
    }

    pub fn on_release(&self) {
        let app = match self.app_handle.lock().clone() {
            Some(app) => app,
            None => return,
        };

        let mut press_time = self.press_time.lock();
        *press_time = None;

        if self.hold_triggered.swap(false, Ordering::SeqCst) {
            info!("Hotkey released, stopping recording");
            self.is_recording.store(false, Ordering::SeqCst);

            // Emit recognizing state
            let _ = app.emit(
                "recording-state",
                serde_json::json!({
                    "state": "recognizing"
                }),
            );

            // Stop recording and get audio data
            let audio_data = if let Some(ref mut recorder) = *APP_STATE.recorder.write() {
                recorder.stop()
            } else {
                Vec::new()
            };

            if audio_data.is_empty() {
                let _ = app.emit(
                    "recognition-error",
                    serde_json::json!({
                        "message": "No audio captured"
                    }),
                );
                return;
            }

            // Perform recognition
            let app_handle = app.clone();
            let config = APP_STATE.config.read().clone();

            std::thread::spawn(move || {
                // Create callback for partial results
                let app_for_partial = app_handle.clone();
                let partial_callback = Box::new(move |text: &str| {
                    let _ = app_for_partial.emit(
                        "partial-result",
                        serde_json::json!({
                            "text": text
                        }),
                    );
                });

                let result = if let Some(ref engine) = *APP_STATE.engine.read() {
                    engine.transcribe_with_callback(
                        &audio_data,
                        &config.core.asr.language,
                        partial_callback,
                    )
                } else {
                    Err("No engine configured".to_string())
                };

                match result {
                    Ok(text) => {
                        info!("Recognition result: {}", text);
                        let _ = app_handle.emit(
                            "final-result",
                            serde_json::json!({
                                "text": text.clone()
                            }),
                        );

                        // Paste text to current application
                        if !text.is_empty() {
                            if let Err(e) = crate::input::paste_text(&app_handle, &text) {
                                error!("Failed to paste text: {}", e);
                            } else {
                                info!("Text pasted successfully");
                            }
                        }

                        // Hide window after a delay
                        std::thread::sleep(Duration::from_millis(500));
                        if let Some(window) = app_handle.get_webview_window("main") {
                            let _ = window.hide();
                        }
                    }
                    Err(e) => {
                        error!("Recognition error: {}", e);
                        let _ = app_handle.emit(
                            "recognition-error",
                            serde_json::json!({
                                "message": e
                            }),
                        );
                    }
                }
            });
        } else {
            info!("Released before hold time, ignoring");
        }
    }
}

/// Convert hotkey string to rdev Key
fn parse_hotkey(hotkey: &str) -> Option<Key> {
    let key = hotkey.to_lowercase();

    match key.as_str() {
        // Modifier keys (now supported with rdev!)
        "ctrl" | "control" => Some(Key::ControlLeft),
        "ctrl_l" | "control_l" => Some(Key::ControlLeft),
        "ctrl_r" | "control_r" => Some(Key::ControlRight),
        "alt" => Some(Key::Alt),
        "alt_l" => Some(Key::Alt),
        "alt_r" => Some(Key::AltGr),
        "shift" => Some(Key::ShiftLeft),
        "shift_l" => Some(Key::ShiftLeft),
        "shift_r" => Some(Key::ShiftRight),
        "cmd" | "super" | "meta" => Some(Key::MetaLeft),
        "cmd_l" | "super_l" | "meta_l" => Some(Key::MetaLeft),
        "cmd_r" | "super_r" | "meta_r" => Some(Key::MetaRight),
        // Function keys
        "f1" => Some(Key::F1),
        "f2" => Some(Key::F2),
        "f3" => Some(Key::F3),
        "f4" => Some(Key::F4),
        "f5" => Some(Key::F5),
        "f6" => Some(Key::F6),
        "f7" => Some(Key::F7),
        "f8" => Some(Key::F8),
        "f9" => Some(Key::F9),
        "f10" => Some(Key::F10),
        "f11" => Some(Key::F11),
        "f12" => Some(Key::F12),
        // Other keys
        "space" => Some(Key::Space),
        "tab" => Some(Key::Tab),
        "caps_lock" | "capslock" => Some(Key::CapsLock),
        "scroll_lock" | "scrolllock" => Some(Key::ScrollLock),
        "pause" => Some(Key::Pause),
        "insert" => Some(Key::Insert),
        "backquote" | "`" => Some(Key::BackQuote),
        _ => None,
    }
}

/// Check if the event key matches the target key
fn key_matches(event_key: &Key, target_key: &Key) -> bool {
    // Handle left/right variants matching generic key
    match (event_key, target_key) {
        // Control key variants
        (Key::ControlLeft, Key::ControlLeft)
        | (Key::ControlRight, Key::ControlLeft)
        | (Key::ControlLeft, Key::ControlRight)
        | (Key::ControlRight, Key::ControlRight) => true,
        // Shift key variants
        (Key::ShiftLeft, Key::ShiftLeft)
        | (Key::ShiftRight, Key::ShiftLeft)
        | (Key::ShiftLeft, Key::ShiftRight)
        | (Key::ShiftRight, Key::ShiftRight) => true,
        // Alt key variants
        (Key::Alt, Key::Alt) | (Key::AltGr, Key::Alt) | (Key::Alt, Key::AltGr) => true,
        // Meta/Super key variants
        (Key::MetaLeft, Key::MetaLeft)
        | (Key::MetaRight, Key::MetaLeft)
        | (Key::MetaLeft, Key::MetaRight)
        | (Key::MetaRight, Key::MetaRight) => true,
        // Exact match for all other keys
        _ => event_key == target_key,
    }
}

/// Start keyboard listener in a separate thread using rdev
pub fn start_keyboard_listener(app: AppHandle) {
    let config = APP_STATE.config.read();
    let hotkey_str = config.core.asr.hotkey.clone();
    let hold_time = config.core.asr.hotkey_hold_time;
    drop(config);

    // Create hotkey manager
    let manager = HotkeyManager::new(&hotkey_str, hold_time);
    manager.set_app_handle(app.clone());
    *APP_STATE.hotkey_manager.write() = Some(manager);

    let target_key = match parse_hotkey(&hotkey_str) {
        Some(key) => key,
        None => {
            error!("Invalid hotkey: {}, using Ctrl as default", hotkey_str);
            Key::ControlLeft
        }
    };

    info!(
        "Starting keyboard listener for hotkey: {} (key: {:?})",
        hotkey_str, target_key
    );

    // Start listener in a separate thread
    std::thread::spawn(move || {
        let callback = move |event: Event| {
            match event.event_type {
                EventType::KeyPress(key) => {
                    if key_matches(&key, &target_key) {
                        if let Some(ref manager) = *APP_STATE.hotkey_manager.read() {
                            manager.on_press();
                        }
                    }
                }
                EventType::KeyRelease(key) => {
                    if key_matches(&key, &target_key) {
                        if let Some(ref manager) = *APP_STATE.hotkey_manager.read() {
                            manager.on_release();
                        }
                    }
                }
                _ => {}
            }
        };

        if let Err(error) = listen(callback) {
            error!("Keyboard listener error: {:?}", error);
        }
    });

    info!("Keyboard listener started");
}

/// Register global hotkeys (now using rdev for modifier key support)
pub fn register_hotkeys(app: AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    start_keyboard_listener(app);
    Ok(())
}
