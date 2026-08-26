use base64::Engine;
use log::{debug, error, info};
use parking_lot::Mutex;
use rdev::{listen, Event, EventType, Key};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, PhysicalPosition};

use crate::APP_STATE;

/// Hotkey manager for handling press-and-hold detection
///
/// This manager monitors keyboard events and triggers actions when the
/// configured hotkey is held for a specified duration.
#[derive(Debug)]
pub struct HotkeyManager {
    hotkey: Arc<Mutex<String>>,
    target_key: Arc<Mutex<Key>>,
    hold_time: Arc<Mutex<Duration>>,
    press_time: Arc<Mutex<Option<Instant>>>,
    hold_triggered: Arc<AtomicBool>,
    app_handle: Arc<Mutex<Option<AppHandle>>>,
}

impl HotkeyManager {
    /// Create a new hotkey manager
    ///
    /// # Arguments
    /// * `hotkey` - String representation of the hotkey
    /// * `hold_time` - Duration (in seconds) the key must be held to trigger
    pub fn new(hotkey: &str, hold_time: f64) -> Self {
        let hotkey_lower = hotkey.to_lowercase();
        let target_key = parse_hotkey(&hotkey_lower).unwrap_or(Key::ControlLeft);
        info!(
            "Initializing HotkeyManager: key={:?}, hold_time={}s",
            target_key, hold_time
        );

        Self {
            hotkey: Arc::new(Mutex::new(hotkey_lower)),
            target_key: Arc::new(Mutex::new(target_key)),
            hold_time: Arc::new(Mutex::new(Duration::from_secs_f64(hold_time))),
            press_time: Arc::new(Mutex::new(None)),
            hold_triggered: Arc::new(AtomicBool::new(false)),
            app_handle: Arc::new(Mutex::new(None)),
        }
    }

    /// Set the application handle for event emission
    pub fn set_app_handle(&self, app: AppHandle) {
        *self.app_handle.lock() = Some(app);
    }

    /// Update the hotkey configuration
    ///
    /// # Arguments
    /// * `hotkey` - New hotkey string
    pub fn update_hotkey(&self, hotkey: &str) {
        let hotkey_lower = hotkey.to_lowercase();
        if let Some(key) = parse_hotkey(&hotkey_lower) {
            *self.target_key.lock() = key;
            *self.hotkey.lock() = hotkey_lower;
            info!("Hotkey updated to: {} (key: {:?})", hotkey, key);
        } else {
            error!("Invalid hotkey: {}", hotkey);
        }
    }

    /// Update the hold time configuration
    ///
    /// # Arguments
    /// * `hold_time` - New hold time in seconds
    pub fn update_hold_time(&self, hold_time: f64) {
        *self.hold_time.lock() = Duration::from_secs_f64(hold_time);
        debug!("Hold time updated to: {}s", hold_time);
    }

    /// Get the current hotkey string
    pub fn get_hotkey(&self) -> String {
        self.hotkey.lock().clone()
    }

    /// Get the current target key
    pub fn get_target_key(&self) -> Key {
        *self.target_key.lock()
    }

    /// Get the current hold time duration
    pub fn get_hold_time(&self) -> Duration {
        *self.hold_time.lock()
    }

    /// Handle hotkey press event
    fn on_press(&self) {
        let app = match self.app_handle.lock().clone() {
            Some(app) => app,
            None => return,
        };

        let mut press_time = self.press_time.lock();
        if press_time.is_none() {
            *press_time = Some(Instant::now());
            let hotkey = self.get_hotkey();
            info!(
                "Hotkey '{}' pressed, waiting {}s for hold...",
                hotkey,
                self.get_hold_time().as_secs_f64()
            );

            // Spawn a timer to check hold time
            let hold_time = self.get_hold_time();
            let press_time_arc = Arc::clone(&self.press_time);
            let hold_triggered = Arc::clone(&self.hold_triggered);
            let app_handle = app.clone();

            std::thread::spawn(move || {
                std::thread::sleep(hold_time);

                // Check if still pressed and not already triggered
                if press_time_arc.lock().is_some() && !hold_triggered.load(Ordering::SeqCst) {
                    hold_triggered.store(true, Ordering::SeqCst);
                    Self::start_recording(&app_handle);
                }
            });
        }
    }

    /// Start recording after hold threshold reached
    fn start_recording(app_handle: &AppHandle) {
        info!("Hold time reached, starting recording");
        // Get focused window info BEFORE showing our window
        let window_info = crate::window_info::get_focused_window_info();

        // Save app info to state for later retrieval
        if let Some(info) = &window_info {
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
                        base64::engine::general_purpose::STANDARD.encode(&data)
                    )
                })
            });

            info!(
                "Saving app info: {} (has icon: {})",
                info.app_name,
                icon_data.is_some()
            );

            // Save to global state
            *APP_STATE.last_focused_app.write() = crate::CachedAppInfo {
                name: info.app_name.clone(),
                icon: icon_data.clone(),
                window_id: Some(info.window_id.clone()),
            };
        }

        // Persist UI state before mapping the hidden webview. On Linux the
        // first event can otherwise arrive before the page registers a
        // listener, leaving the floating window in its idle placeholder.
        {
            let app_info = APP_STATE.last_focused_app.read().clone();
            let mut ui = APP_STATE.ui.write();
            ui.phase = "recording".to_string();
            ui.audio_level = 0.0;
            ui.partial_result.clear();
            ui.final_result.clear();
            ui.error_message.clear();
            ui.app_name = app_info.name;
            ui.app_icon = app_info.icon;
        }

        // Show the floating window without requesting focus. Keeping the
        // original target focused is what makes the later paste land in the
        // user's editor instead of in Speaky itself.
        if let Some(window) = app_handle.get_webview_window("main") {
            let _ = window.show();
            // Mutter applies the configured initial centering when a hidden
            // window is mapped for the first time, overriding any position
            // set beforehand. Move it immediately after mapping instead.
            position_floating_window(
                &window,
                window_info.as_ref().map(|info| info.window_id.as_str()),
            );
        }

        // Emit recording state event
        let _ = app_handle.emit(
            "recording-state",
            serde_json::json!({
                "state": "started"
            }),
        );

        // Start audio recording
        if let Some(ref mut recorder) = *APP_STATE.recorder.write() {
            // Set up audio level callback
            let app_for_level = app_handle.clone();
            recorder.set_audio_level_callback(move |level| {
                // Multiply by 3 to match Python implementation
                APP_STATE.ui.write().audio_level = level * 3.0;
                let _ = app_for_level.emit(
                    "audio-level",
                    serde_json::json!({
                        "level": level * 3.0
                    }),
                );
            });

            // In streaming mode connect before recording and feed converted
            // PCM chunks directly to the WebSocket while the key is held.
            let config = APP_STATE.config.read().clone();
            if config.core.asr.streaming_mode && config.engine.current == "volc_bigmodel" {
                let api_key = if config.engine.volc_bigmodel.api_key.is_empty() {
                    std::env::var("SPEAKY_VOLC_API_KEY").unwrap_or_default()
                } else {
                    config.engine.volc_bigmodel.api_key.clone()
                };
                let engine = crate::engines::VolcBigModelEngine::new(
                    &api_key,
                    &config.engine.volc_bigmodel.app_key,
                    &config.engine.volc_bigmodel.access_key,
                    &config.engine.volc_bigmodel.resource_id,
                );
                let app_for_partial = app_handle.clone();
                let session = engine.start_realtime(Box::new(move |text: &str| {
                    APP_STATE.ui.write().partial_result = text.to_string();
                    let _ =
                        app_for_partial.emit("partial-result", serde_json::json!({"text": text}));
                }));
                let audio_sender = session.audio_sender();
                recorder.set_audio_data_callback(move |pcm| audio_sender.send(pcm));
                *APP_STATE.realtime_session.write() = Some(session);
            } else {
                recorder.clear_audio_data_callback();
                *APP_STATE.realtime_session.write() = None;
            }

            if let Err(e) = recorder.start() {
                error!("Failed to start recording: {}", e);
                crate::sound::play(crate::sound::Cue::Error);
                let mut ui = APP_STATE.ui.write();
                ui.phase = "error".to_string();
                ui.error_message = e.clone();
                let _ = app_handle.emit(
                    "recognition-error",
                    serde_json::json!({
                        "message": e
                    }),
                );
            } else {
                crate::sound::play(crate::sound::Cue::Start);
            }
        }
    }

    /// Handle hotkey release event
    fn on_release(&self) {
        let app = match self.app_handle.lock().clone() {
            Some(app) => app,
            None => return,
        };

        let mut press_time = self.press_time.lock();
        *press_time = None;

        if self.hold_triggered.swap(false, Ordering::SeqCst) {
            info!("Hotkey released, stopping recording");
            APP_STATE.ui.write().phase = "recognizing".to_string();
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
            crate::sound::play(crate::sound::Cue::End);

            if audio_data.is_empty() {
                crate::sound::play(crate::sound::Cue::Error);
                let mut ui = APP_STATE.ui.write();
                ui.phase = "error".to_string();
                ui.error_message = "No audio captured".to_string();
                let _ = app.emit(
                    "recognition-error",
                    serde_json::json!({
                        "message": "No audio captured"
                    }),
                );
                return;
            }

            if let Some(session) = APP_STATE.realtime_session.write().take() {
                std::thread::spawn(move || {
                    // Keep realtime captions while the key is held, then run
                    // the complete WAV through the more accurate final model.
                    // Both requests finish concurrently, so correction adds
                    // little latency and safely falls back to realtime.
                    let config = APP_STATE.config.read().clone();
                    let correction_audio = audio_data;
                    let correction = std::thread::spawn(move || {
                        let api_key = if config.engine.volc_bigmodel.api_key.is_empty() {
                            std::env::var("SPEAKY_VOLC_API_KEY").unwrap_or_default()
                        } else {
                            config.engine.volc_bigmodel.api_key.clone()
                        };
                        let engine = crate::engines::VolcBigModelEngine::new(
                            &api_key,
                            &config.engine.volc_bigmodel.app_key,
                            &config.engine.volc_bigmodel.access_key,
                            &config.engine.volc_bigmodel.resource_id,
                        );
                        engine.transcribe_final(&correction_audio, &config.core.asr.language)
                    });

                    let realtime_result = session.finish();
                    let result = match correction.join() {
                        Ok(Ok(text)) if !text.trim().is_empty() => Ok(text),
                        Ok(Err(error)) => {
                            error!(
                                "Final accuracy pass failed, using realtime result: {}",
                                error
                            );
                            realtime_result
                        }
                        Ok(Ok(_)) => realtime_result,
                        Err(_) => {
                            error!("Final accuracy pass panicked, using realtime result");
                            realtime_result
                        }
                    };
                    deliver_recognition_result(app, result);
                });
            } else {
                recognize_and_deliver(app, audio_data);
            }
        } else {
            info!("Released before hold time threshold, ignoring");
        }
    }
}

/// Place the recording overlay near the bottom center of the monitor that
/// contains the target application. Monitor positions and window geometry are
/// both physical desktop coordinates, including negative coordinates in
/// left/upper multi-monitor layouts.
fn position_floating_window(window: &tauri::WebviewWindow, target_window_id: Option<&str>) {
    const BOTTOM_MARGIN: i32 = 56;

    let monitors = match window.available_monitors() {
        Ok(monitors) if !monitors.is_empty() => monitors,
        Ok(_) => return,
        Err(error) => {
            error!("Failed to enumerate monitors: {}", error);
            return;
        }
    };

    let target_center = target_window_id.and_then(crate::window_info::window_center);
    let selected = target_center
        .and_then(|(x, y)| {
            monitors.iter().find(|monitor| {
                let origin = monitor.position();
                let size = monitor.size();
                let right = origin.x.saturating_add(size.width as i32);
                let bottom = origin.y.saturating_add(size.height as i32);
                x >= origin.x && x < right && y >= origin.y && y < bottom
            })
        })
        .or_else(|| monitors.first());

    let Some(monitor) = selected else {
        return;
    };
    let overlay_size = match window.outer_size() {
        Ok(size) => size,
        Err(error) => {
            error!("Failed to read floating window size: {}", error);
            return;
        }
    };
    let origin = monitor.position();
    let monitor_size = monitor.size();
    let x = origin.x + ((monitor_size.width as i64 - overlay_size.width as i64) / 2).max(0) as i32;
    let y = origin.y
        + (monitor_size.height as i64 - overlay_size.height as i64 - BOTTOM_MARGIN as i64).max(0)
            as i32;

    match window.set_position(PhysicalPosition::new(x, y)) {
        Ok(()) => info!(
            "Positioned floating window at ({}, {}) on target monitor (target center: {:?})",
            x, y, target_center
        ),
        Err(error) => error!("Failed to position floating window: {}", error),
    }
}

/// Recognize captured WAV audio and deliver the result to the UI and the
/// previously focused application. The work is performed off the keyboard
/// listener thread so a slow network request never blocks hotkey handling.
pub fn recognize_and_deliver(app_handle: AppHandle, audio_data: Vec<u8>) {
    if audio_data.is_empty() {
        let _ = app_handle.emit(
            "recognition-error",
            serde_json::json!({"message": "No audio captured"}),
        );
        return;
    }

    let config = APP_STATE.config.read().clone();

    std::thread::spawn(move || {
        let result = if let Some(ref engine) = *APP_STATE.engine.read() {
            if config.core.asr.streaming_mode {
                let app_for_partial = app_handle.clone();
                let partial_callback = Box::new(move |text: &str| {
                    APP_STATE.ui.write().partial_result = text.to_string();
                    let _ =
                        app_for_partial.emit("partial-result", serde_json::json!({"text": text}));
                });
                engine.transcribe_with_callback(
                    &audio_data,
                    &config.core.asr.language,
                    partial_callback,
                )
            } else {
                engine.transcribe(&audio_data, &config.core.asr.language)
            }
        } else {
            Err(crate::engines::EngineError::NotConfigured)
        };

        deliver_recognition_result(app_handle, result);
    });
}

fn deliver_recognition_result(app_handle: AppHandle, result: crate::engines::EngineResult) {
    match result {
        Ok(original_text) => {
            info!("Recognition result: {} chars", original_text.len());
            if original_text.trim().is_empty() {
                crate::sound::play(crate::sound::Cue::Error);
                let mut ui = APP_STATE.ui.write();
                ui.phase = "error".to_string();
                ui.error_message = "识别结果为空，请确认麦克风有声音".to_string();
                drop(ui);
                let _ = app_handle.emit(
                    "recognition-error",
                    serde_json::json!({"message": "识别结果为空，请确认麦克风有声音"}),
                );
                std::thread::sleep(Duration::from_secs(2));
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ = window.hide();
                }
                return;
            }

            let config = APP_STATE.config.read().clone();
            let mut polished = false;
            let text = if config.core.asr.llm_polish {
                {
                    let mut ui = APP_STATE.ui.write();
                    ui.phase = "polishing".to_string();
                    ui.partial_result.clear();
                }
                let _ =
                    app_handle.emit("recording-state", serde_json::json!({"state": "polishing"}));
                let app_for_partial = app_handle.clone();
                match crate::polish::polish(&config, &original_text, move |partial| {
                    APP_STATE.ui.write().partial_result = partial.to_string();
                    let _ = app_for_partial
                        .emit("partial-result", serde_json::json!({"text": partial}));
                }) {
                    Ok(result) => {
                        polished = true;
                        info!("AI polish completed: {} chars", result.len());
                        result
                    }
                    Err(error) => {
                        error!("AI polish failed; using original recognition: {}", error);
                        original_text
                    }
                }
            } else {
                original_text
            };

            let engine_name = APP_STATE
                .engine
                .read()
                .as_ref()
                .map(|engine| engine.name().to_string())
                .unwrap_or_default();
            crate::history::add(&text, &engine_name, polished);
            crate::tray::refresh(&app_handle);

            {
                let mut ui = APP_STATE.ui.write();
                ui.phase = "done".to_string();
                ui.final_result = text.clone();
                ui.partial_result.clear();
                ui.error_message.clear();
            }
            let _ = app_handle.emit("final-result", serde_json::json!({"text": text.clone()}));

            // Mapping the floating window can change focus on some Linux
            // window managers even when it is marked non-focusable.
            // Restore the exact window that was active at key-down.
            if let Some(window_id) = APP_STATE.last_focused_app.read().window_id.clone() {
                match crate::window_info::focus_window(&window_id) {
                    Ok(()) => {
                        info!("Restored target window focus before paste");
                        std::thread::sleep(Duration::from_millis(100));
                    }
                    Err(error) => {
                        error!("Failed to restore target window focus: {}", error);
                    }
                }
            }

            if let Err(e) = crate::input::paste_text(&app_handle, &text) {
                error!("Failed to paste text: {}", e);
                let mut ui = APP_STATE.ui.write();
                ui.phase = "error".to_string();
                ui.error_message = e.to_string();
                drop(ui);
                let _ = app_handle.emit(
                    "recognition-error",
                    serde_json::json!({"message": e.to_string()}),
                );
            } else {
                info!("Text pasted successfully");
            }

            // Keep the final result visible long enough to be readable.
            std::thread::sleep(Duration::from_secs(2));
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = window.hide();
            }
        }
        Err(e) => {
            error!("Recognition error: {}", e);
            crate::sound::play(crate::sound::Cue::Error);
            let mut ui = APP_STATE.ui.write();
            ui.phase = "error".to_string();
            ui.error_message = e.to_string();
            drop(ui);
            let _ = app_handle.emit(
                "recognition-error",
                serde_json::json!({"message": e.to_string()}),
            );
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

    info!(
        "Starting keyboard listener for hotkey: '{}' (key: {:?})",
        hotkey_str,
        parse_hotkey(&hotkey_str)
    );

    // Start listener in a separate thread
    std::thread::spawn(move || {
        let callback = move |event: Event| {
            // Get current target key from manager (allows dynamic updates)
            let target_key = if let Some(ref manager) = *APP_STATE.hotkey_manager.read() {
                manager.get_target_key()
            } else {
                return;
            };

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

    info!("Keyboard listener started successfully");
}

/// Register global hotkeys (now using rdev for modifier key support)
pub fn register_hotkeys(app: AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    start_keyboard_listener(app);
    Ok(())
}
