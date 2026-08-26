use base64::Engine;
use log::{debug, error, info};
use parking_lot::Mutex;
use rdev::{listen, Event, EventType, Key};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, PhysicalPosition};

use crate::APP_STATE;

static RECOGNITION_GENERATION: AtomicU64 = AtomicU64::new(0);
static RECORDING_CANCEL_REQUESTED: AtomicBool = AtomicBool::new(false);

/// Hotkey manager for handling press-and-hold detection
///
/// This manager monitors keyboard events and triggers actions when the
/// configured hotkey is held for a specified duration.
#[derive(Debug)]
pub struct HotkeyManager {
    hotkey: Arc<Mutex<String>>,
    target_key: Arc<Mutex<Key>>,
    capture_requested: Arc<AtomicBool>,
    hold_time: Arc<Mutex<Duration>>,
    press_time: Arc<Mutex<Option<Instant>>>,
    hold_triggered: Arc<AtomicBool>,
    combo_suppressed: Arc<AtomicBool>,
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
            capture_requested: Arc::new(AtomicBool::new(false)),
            hold_time: Arc::new(Mutex::new(Duration::from_secs_f64(hold_time))),
            press_time: Arc::new(Mutex::new(None)),
            hold_triggered: Arc::new(AtomicBool::new(false)),
            combo_suppressed: Arc::new(AtomicBool::new(false)),
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

    /// Capture the next globally reported keyboard press for the settings UI.
    pub fn begin_capture(&self) {
        self.capture_requested.store(true, Ordering::SeqCst);
        info!("Waiting for the user to choose a hotkey");
    }

    pub fn cancel_capture(&self) {
        self.capture_requested.store(false, Ordering::SeqCst);
    }

    fn try_capture(&self, key: Key) -> bool {
        if !self.capture_requested.load(Ordering::SeqCst) {
            return false;
        }

        let key = normalize_event_key(key);
        let Some(value) = hotkey_name(key) else {
            if let Some(app) = self.app_handle.lock().clone() {
                let _ = app.emit(
                    "hotkey-capture-error",
                    serde_json::json!({"message": "unsupported-key"}),
                );
            }
            return true;
        };

        self.capture_requested.store(false, Ordering::SeqCst);
        if let Some(app) = self.app_handle.lock().clone() {
            let _ = app.emit("hotkey-captured", serde_json::json!({"hotkey": value}));
        }
        info!("Captured hotkey: {} ({:?})", value, key);
        true
    }

    fn matches(&self, event_key: Key) -> bool {
        let target_key = self.get_target_key();
        let hotkey = self.get_hotkey();
        key_matches(&normalize_event_key(event_key), &target_key, &hotkey)
    }

    /// A configured modifier must not fire when it is being used as part of a
    /// normal shortcut (for example Ctrl+V in a browser terminal). Cancel the
    /// pending hold as soon as another key arrives while the trigger is down.
    fn cancel_for_combination(&self) {
        // Once recording has started, the trigger release must still stop it;
        // only suppress the pending hold window.
        if self.hold_triggered.load(Ordering::SeqCst) {
            return;
        }
        let mut press_time = self.press_time.lock();
        if press_time.take().is_some() {
            self.combo_suppressed.store(true, Ordering::SeqCst);
            info!("Hotkey hold cancelled because it is part of a key combination");
        }
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
            self.combo_suppressed.store(false, Ordering::SeqCst);
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
                    if !Self::start_recording(&app_handle) {
                        hold_triggered.store(false, Ordering::SeqCst);
                    }
                }
            });
        }
    }

    /// Start recording after hold threshold reached
    fn start_recording(app_handle: &AppHandle) -> bool {
        info!("Hold time reached, starting recording");
        RECORDING_CANCEL_REQUESTED.store(false, Ordering::SeqCst);
        RECOGNITION_GENERATION.fetch_add(1, Ordering::SeqCst);
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

        if APP_STATE.engine.read().is_none() {
            fail_and_hide(app_handle, "识别引擎尚未配置，请先在设置中填写 API Key");
            return false;
        }

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
                APP_STATE.realtime_session.write().take();
                fail_and_hide(app_handle, &e);
                return false;
            } else {
                if RECORDING_CANCEL_REQUESTED.load(Ordering::SeqCst) {
                    let _ = recorder.stop();
                    APP_STATE.realtime_session.write().take();
                    fail_and_hide(app_handle, "录音启动后按键已松开");
                    return false;
                }
                crate::sound::play(crate::sound::Cue::Start);
                return true;
            }
        }
        fail_and_hide(app_handle, "麦克风尚未就绪，请在诊断页检查设备");
        false
    }

    /// Handle hotkey release event
    fn on_release(&self) {
        let app = match self.app_handle.lock().clone() {
            Some(app) => app,
            None => return,
        };

        let mut press_time = self.press_time.lock();
        *press_time = None;

        if self.combo_suppressed.swap(false, Ordering::SeqCst) {
            info!("Hotkey release ignored after a key combination");
            return;
        }

        if self.hold_triggered.swap(false, Ordering::SeqCst) {
            info!("Hotkey released, stopping recording");
            RECORDING_CANCEL_REQUESTED.store(true, Ordering::SeqCst);
            APP_STATE.ui.write().phase = "recognizing".to_string();
            // Emit recognizing state
            let _ = app.emit(
                "recording-state",
                serde_json::json!({
                    "state": "recognizing"
                }),
            );

            // Stop recording and get audio data
            let stop_started = Instant::now();
            let audio_data = loop {
                if let Some(mut recorder_guard) = APP_STATE.recorder.try_write() {
                    break if let Some(ref mut recorder) = *recorder_guard {
                        recorder.stop()
                    } else {
                        Vec::new()
                    };
                }
                if stop_started.elapsed() >= Duration::from_secs(5) {
                    APP_STATE.realtime_session.write().take();
                    fail_and_hide(&app, "录音设备启动超时，请在诊断页检查麦克风");
                    return;
                }
                std::thread::sleep(Duration::from_millis(25));
            };
            crate::sound::play(crate::sound::Cue::End);

            if audio_data.is_empty() {
                APP_STATE.realtime_session.write().take();
                fail_and_hide(&app, "没有采集到音频，请检查麦克风设备");
                return;
            }

            let generation = RECOGNITION_GENERATION.load(Ordering::SeqCst);
            arm_recognition_watchdog(&app, generation);

            if let Some(session) = APP_STATE.realtime_session.write().take() {
                std::thread::spawn(move || {
                    // The realtime hypothesis is the primary result. Deliver
                    // it as soon as the stream closes; a second correction
                    // request must never hold the UI in "recognizing". If the
                    // realtime endpoint returns no text, use the final
                    // endpoint as a bounded fallback for short utterances.
                    let realtime_result = session.finish();
                    let has_realtime_text =
                        matches!(&realtime_result, Ok(text) if !text.trim().is_empty());
                    if has_realtime_text {
                        info!("Delivering realtime recognition result immediately");
                        deliver_recognition_result(app, realtime_result, generation);
                        return;
                    }

                    let config = APP_STATE.config.read().clone();
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
                    let fallback = engine.transcribe_final(&audio_data, &config.core.asr.language);
                    if fallback.is_ok() {
                        info!("Realtime result was empty; delivered final recognition fallback");
                        deliver_recognition_result(app, fallback, generation);
                    } else {
                        deliver_recognition_result(app, realtime_result, generation);
                    }
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
        fail_and_hide(&app_handle, "没有采集到音频，请检查麦克风设备");
        return;
    }

    let config = APP_STATE.config.read().clone();
    let generation = RECOGNITION_GENERATION.load(Ordering::SeqCst);
    arm_recognition_watchdog(&app_handle, generation);

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

        deliver_recognition_result(app_handle, result, generation);
    });
}

fn deliver_recognition_result(
    app_handle: AppHandle,
    result: crate::engines::EngineResult,
    generation: u64,
) {
    if generation != RECOGNITION_GENERATION.load(Ordering::SeqCst) {
        info!("Discarding stale recognition result");
        return;
    }
    match result {
        Ok(original_text) => {
            info!("Recognition result: {} chars", original_text.len());
            if original_text.trim().is_empty() {
                fail_and_hide(&app_handle, "识别结果为空，请确认麦克风有声音");
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

            if generation != RECOGNITION_GENERATION.load(Ordering::SeqCst) {
                info!("Discarding recognition result after timeout or a newer recording");
                return;
            }

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
            fail_and_hide(&app_handle, &e.to_string());
        }
    }
}

fn fail_and_hide(app_handle: &AppHandle, message: &str) {
    // Invalidate any realtime worker that may still be finishing in the
    // background; a late response must not resurrect the overlay.
    RECOGNITION_GENERATION.fetch_add(1, Ordering::SeqCst);
    crate::sound::play(crate::sound::Cue::Error);
    {
        let mut ui = APP_STATE.ui.write();
        ui.phase = "error".to_string();
        ui.error_message = message.to_string();
    }
    let _ = app_handle.emit("recognition-error", serde_json::json!({"message": message}));

    let app = app_handle.clone();
    let expected_message = message.to_string();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(2));
        let should_hide = {
            let mut ui = APP_STATE.ui.write();
            if ui.phase == "error" && ui.error_message == expected_message {
                ui.phase = "idle".to_string();
                ui.audio_level = 0.0;
                ui.partial_result.clear();
                ui.final_result.clear();
                ui.error_message.clear();
                true
            } else {
                false
            }
        };
        if should_hide {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.hide();
            }
        }
    });
}

fn arm_recognition_watchdog(app_handle: &AppHandle, generation: u64) {
    let app = app_handle.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(30));
        if generation != RECOGNITION_GENERATION.load(Ordering::SeqCst) {
            return;
        }
        let stalled = matches!(
            APP_STATE.ui.read().phase.as_str(),
            "recognizing" | "polishing"
        );
        if stalled
            && RECOGNITION_GENERATION
                .compare_exchange(
                    generation,
                    generation.wrapping_add(1),
                    Ordering::SeqCst,
                    Ordering::SeqCst,
                )
                .is_ok()
        {
            error!("Recognition watchdog timed out");
            fail_and_hide(&app, "识别超时，请检查网络或识别引擎配置");
        }
    });
}

/// Convert hotkey string to rdev Key
pub(crate) fn parse_hotkey(hotkey: &str) -> Option<Key> {
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
        "fn" | "function" => Some(Key::Function),
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
        "escape" | "esc" => Some(Key::Escape),
        "enter" | "return" => Some(Key::Return),
        "backspace" => Some(Key::Backspace),
        "delete" => Some(Key::Delete),
        "home" => Some(Key::Home),
        "end" => Some(Key::End),
        "page_up" | "pageup" => Some(Key::PageUp),
        "page_down" | "pagedown" => Some(Key::PageDown),
        "arrow_up" | "up" => Some(Key::UpArrow),
        "arrow_down" | "down" => Some(Key::DownArrow),
        "arrow_left" | "left" => Some(Key::LeftArrow),
        "arrow_right" | "right" => Some(Key::RightArrow),
        "print_screen" | "printscreen" => Some(Key::PrintScreen),
        "num_lock" | "numlock" => Some(Key::NumLock),
        "0" => Some(Key::Num0),
        "1" => Some(Key::Num1),
        "2" => Some(Key::Num2),
        "3" => Some(Key::Num3),
        "4" => Some(Key::Num4),
        "5" => Some(Key::Num5),
        "6" => Some(Key::Num6),
        "7" => Some(Key::Num7),
        "8" => Some(Key::Num8),
        "9" => Some(Key::Num9),
        "a" => Some(Key::KeyA),
        "b" => Some(Key::KeyB),
        "c" => Some(Key::KeyC),
        "d" => Some(Key::KeyD),
        "e" => Some(Key::KeyE),
        "f" => Some(Key::KeyF),
        "g" => Some(Key::KeyG),
        "h" => Some(Key::KeyH),
        "i" => Some(Key::KeyI),
        "j" => Some(Key::KeyJ),
        "k" => Some(Key::KeyK),
        "l" => Some(Key::KeyL),
        "m" => Some(Key::KeyM),
        "n" => Some(Key::KeyN),
        "o" => Some(Key::KeyO),
        "p" => Some(Key::KeyP),
        "q" => Some(Key::KeyQ),
        "r" => Some(Key::KeyR),
        "s" => Some(Key::KeyS),
        "t" => Some(Key::KeyT),
        "u" => Some(Key::KeyU),
        "v" => Some(Key::KeyV),
        "w" => Some(Key::KeyW),
        "x" => Some(Key::KeyX),
        "y" => Some(Key::KeyY),
        "z" => Some(Key::KeyZ),
        "minus" => Some(Key::Minus),
        "equal" => Some(Key::Equal),
        "left_bracket" => Some(Key::LeftBracket),
        "right_bracket" => Some(Key::RightBracket),
        "semicolon" => Some(Key::SemiColon),
        "quote" => Some(Key::Quote),
        "backslash" => Some(Key::BackSlash),
        "intl_backslash" => Some(Key::IntlBackslash),
        "comma" => Some(Key::Comma),
        "dot" | "period" => Some(Key::Dot),
        "slash" => Some(Key::Slash),
        "numpad_0" => Some(Key::Kp0),
        "numpad_1" => Some(Key::Kp1),
        "numpad_2" => Some(Key::Kp2),
        "numpad_3" => Some(Key::Kp3),
        "numpad_4" => Some(Key::Kp4),
        "numpad_5" => Some(Key::Kp5),
        "numpad_6" => Some(Key::Kp6),
        "numpad_7" => Some(Key::Kp7),
        "numpad_8" => Some(Key::Kp8),
        "numpad_9" => Some(Key::Kp9),
        "numpad_enter" => Some(Key::KpReturn),
        "numpad_minus" => Some(Key::KpMinus),
        "numpad_plus" => Some(Key::KpPlus),
        "numpad_multiply" => Some(Key::KpMultiply),
        "numpad_divide" => Some(Key::KpDivide),
        "numpad_delete" => Some(Key::KpDelete),
        _ => None,
    }
}

pub(crate) fn is_supported_hotkey(hotkey: &str) -> bool {
    parse_hotkey(hotkey).is_some()
}

fn hotkey_name(key: Key) -> Option<&'static str> {
    Some(match key {
        Key::Alt => "alt_l",
        Key::AltGr => "alt_r",
        Key::Backspace => "backspace",
        Key::CapsLock => "caps_lock",
        Key::ControlLeft => "ctrl_l",
        Key::ControlRight => "ctrl_r",
        Key::Delete => "delete",
        Key::DownArrow => "arrow_down",
        Key::End => "end",
        Key::Escape => "escape",
        Key::F1 => "f1",
        Key::F2 => "f2",
        Key::F3 => "f3",
        Key::F4 => "f4",
        Key::F5 => "f5",
        Key::F6 => "f6",
        Key::F7 => "f7",
        Key::F8 => "f8",
        Key::F9 => "f9",
        Key::F10 => "f10",
        Key::F11 => "f11",
        Key::F12 => "f12",
        Key::Home => "home",
        Key::LeftArrow => "arrow_left",
        Key::MetaLeft => "cmd_l",
        Key::MetaRight => "cmd_r",
        Key::PageDown => "page_down",
        Key::PageUp => "page_up",
        Key::Return => "enter",
        Key::RightArrow => "arrow_right",
        Key::ShiftLeft => "shift_l",
        Key::ShiftRight => "shift_r",
        Key::Space => "space",
        Key::Tab => "tab",
        Key::UpArrow => "arrow_up",
        Key::PrintScreen => "print_screen",
        Key::ScrollLock => "scroll_lock",
        Key::Pause => "pause",
        Key::NumLock => "num_lock",
        Key::BackQuote => "backquote",
        Key::Num0 => "0",
        Key::Num1 => "1",
        Key::Num2 => "2",
        Key::Num3 => "3",
        Key::Num4 => "4",
        Key::Num5 => "5",
        Key::Num6 => "6",
        Key::Num7 => "7",
        Key::Num8 => "8",
        Key::Num9 => "9",
        Key::Minus => "minus",
        Key::Equal => "equal",
        Key::KeyQ => "q",
        Key::KeyW => "w",
        Key::KeyE => "e",
        Key::KeyR => "r",
        Key::KeyT => "t",
        Key::KeyY => "y",
        Key::KeyU => "u",
        Key::KeyI => "i",
        Key::KeyO => "o",
        Key::KeyP => "p",
        Key::LeftBracket => "left_bracket",
        Key::RightBracket => "right_bracket",
        Key::KeyA => "a",
        Key::KeyS => "s",
        Key::KeyD => "d",
        Key::KeyF => "f",
        Key::KeyG => "g",
        Key::KeyH => "h",
        Key::KeyJ => "j",
        Key::KeyK => "k",
        Key::KeyL => "l",
        Key::SemiColon => "semicolon",
        Key::Quote => "quote",
        Key::BackSlash => "backslash",
        Key::IntlBackslash => "intl_backslash",
        Key::KeyZ => "z",
        Key::KeyX => "x",
        Key::KeyC => "c",
        Key::KeyV => "v",
        Key::KeyB => "b",
        Key::KeyN => "n",
        Key::KeyM => "m",
        Key::Comma => "comma",
        Key::Dot => "dot",
        Key::Slash => "slash",
        Key::Insert => "insert",
        Key::KpReturn => "numpad_enter",
        Key::KpMinus => "numpad_minus",
        Key::KpPlus => "numpad_plus",
        Key::KpMultiply => "numpad_multiply",
        Key::KpDivide => "numpad_divide",
        Key::Kp0 => "numpad_0",
        Key::Kp1 => "numpad_1",
        Key::Kp2 => "numpad_2",
        Key::Kp3 => "numpad_3",
        Key::Kp4 => "numpad_4",
        Key::Kp5 => "numpad_5",
        Key::Kp6 => "numpad_6",
        Key::Kp7 => "numpad_7",
        Key::Kp8 => "numpad_8",
        Key::Kp9 => "numpad_9",
        Key::KpDelete => "numpad_delete",
        Key::Function => "fn",
        Key::Unknown(_) => return None,
    })
}

fn normalize_event_key(key: Key) -> Key {
    match key {
        #[cfg(target_os = "windows")]
        Key::Unknown(92) => Key::MetaRight,
        #[cfg(target_os = "linux")]
        Key::Unknown(134) => Key::MetaRight,
        _ => key,
    }
}

/// Check if the event key matches the target key
fn key_matches(event_key: &Key, target_key: &Key, configured_hotkey: &str) -> bool {
    // Preserve the historical generic aliases while allowing native capture
    // to distinguish the physical left and right modifier keys.
    match configured_hotkey {
        "ctrl" | "control" => return matches!(event_key, Key::ControlLeft | Key::ControlRight),
        "shift" => return matches!(event_key, Key::ShiftLeft | Key::ShiftRight),
        "alt" => return matches!(event_key, Key::Alt | Key::AltGr),
        "cmd" | "super" | "meta" => return matches!(event_key, Key::MetaLeft | Key::MetaRight),
        _ => {}
    }

    match (event_key, target_key) {
        // Control key variants
        (Key::ControlLeft, Key::ControlLeft) | (Key::ControlRight, Key::ControlRight) => true,
        // Shift key variants
        (Key::ShiftLeft, Key::ShiftLeft) | (Key::ShiftRight, Key::ShiftRight) => true,
        // Alt key variants
        (Key::Alt, Key::Alt) | (Key::AltGr, Key::AltGr) => true,
        // Meta/Super key variants
        (Key::MetaLeft, Key::MetaLeft) | (Key::MetaRight, Key::MetaRight) => true,
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
        let callback = move |event: Event| match event.event_type {
            EventType::KeyPress(key) => {
                if let Some(ref manager) = *APP_STATE.hotkey_manager.read() {
                    if manager.try_capture(key) {
                        return;
                    }
                    if manager.matches(key) {
                        manager.on_press();
                    } else {
                        manager.cancel_for_combination();
                    }
                }
            }
            EventType::KeyRelease(key) => {
                if let Some(ref manager) = *APP_STATE.hotkey_manager.read() {
                    if manager.matches(key) {
                        manager.on_release();
                    }
                }
            }
            _ => {}
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_native_system_and_function_keys() {
        assert_eq!(parse_hotkey("cmd_l"), Some(Key::MetaLeft));
        assert_eq!(parse_hotkey("cmd_r"), Some(Key::MetaRight));
        assert_eq!(parse_hotkey("fn"), Some(Key::Function));
        assert_eq!(parse_hotkey("f12"), Some(Key::F12));
        assert_eq!(parse_hotkey("numpad_5"), Some(Key::Kp5));
        assert!(parse_hotkey("not-a-key").is_none());
    }

    #[test]
    fn captured_modifiers_keep_their_physical_side() {
        assert!(key_matches(&Key::ControlLeft, &Key::ControlLeft, "ctrl_l"));
        assert!(!key_matches(
            &Key::ControlRight,
            &Key::ControlLeft,
            "ctrl_l"
        ));
        assert!(key_matches(&Key::ControlRight, &Key::ControlLeft, "ctrl"));
        assert!(key_matches(&Key::MetaRight, &Key::MetaRight, "cmd_r"));
        assert!(!key_matches(&Key::MetaLeft, &Key::MetaRight, "cmd_r"));
    }

    #[test]
    fn modifier_hold_is_cancelled_by_a_following_key() {
        let manager = HotkeyManager::new("ctrl", 1.0);
        *manager.press_time.lock() = Some(Instant::now());

        manager.cancel_for_combination();

        assert!(manager.press_time.lock().is_none());
        assert!(manager.combo_suppressed.load(Ordering::SeqCst));
    }
}
