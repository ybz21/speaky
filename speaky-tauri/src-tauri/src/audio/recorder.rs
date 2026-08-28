use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, SampleFormat, Stream, StreamConfig};
use log::{debug, error, info, warn};
use parking_lot::Mutex;
use std::collections::HashSet;
#[cfg(target_os = "linux")]
use std::io::Read;
#[cfg(target_os = "linux")]
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
#[cfg(target_os = "linux")]
use std::thread::JoinHandle;
use std::time::Duration;

/// Audio format constants
const SAMPLE_RATE: u32 = 16000;
const CHANNELS: u16 = 1;
const SAMPLE_WIDTH: u16 = 2; // 16-bit

/// Rank automatic input candidates. Physical USB microphones are generally
/// more reliable than ALSA/PipeWire compatibility endpoints, while monitor
/// and loopback sources should never win automatic microphone selection.
fn automatic_device_priority(name: &str) -> (bool, bool, bool, String) {
    let normalized = name.trim().to_lowercase();
    let monitor = normalized.contains("monitor") || normalized.contains("loopback");
    let generic = matches!(
        normalized.as_str(),
        "default" | "pipewire" | "pulse" | "sysdefault"
    );
    let usb = normalized.contains("usb");
    (monitor, generic, !usb, normalized)
}

fn device_name_matches(candidate: &str, detected: &str) -> bool {
    let candidate = candidate.trim().to_lowercase();
    let detected = detected.trim().to_lowercase();
    candidate == detected
        || (candidate.len() >= 6 && detected.contains(&candidate))
        || (detected.len() >= 6 && candidate.contains(&detected))
}

#[cfg(target_os = "linux")]
#[derive(Clone, Debug)]
struct PipeWireSource {
    stable_name: String,
    display_name: String,
    target: String,
    aliases: Vec<String>,
}

#[cfg(target_os = "linux")]
fn pipewire_command(program: &str) -> Command {
    let mut command = Command::new(program);
    // Desktop launchers normally provide these. Keeping the conventional
    // per-user paths as a fallback also makes diagnostics and packaged-app
    // launches work when an intermediate launcher sanitizes the environment.
    if std::env::var_os("XDG_RUNTIME_DIR").is_none() {
        if let Ok(output) = Command::new("id").arg("-u").output() {
            let uid = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !uid.is_empty() {
                let runtime = format!("/run/user/{uid}");
                command.env("XDG_RUNTIME_DIR", &runtime);
                if std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_none() {
                    command.env(
                        "DBUS_SESSION_BUS_ADDRESS",
                        format!("unix:path={runtime}/bus"),
                    );
                }
            }
        }
    }
    command
}

#[cfg(target_os = "linux")]
fn pipewire_sources() -> Vec<PipeWireSource> {
    let mut output = None;
    for attempt in 0..3 {
        match pipewire_command("pw-dump").output() {
            Ok(candidate) if candidate.status.success() => {
                output = Some(candidate.stdout);
                break;
            }
            _ if attempt < 2 => std::thread::sleep(Duration::from_millis(75)),
            _ => {}
        }
    }
    let Some(output) = output else {
        return Vec::new();
    };
    let Ok(objects) = serde_json::from_slice::<Vec<serde_json::Value>>(&output) else {
        return Vec::new();
    };

    let mut sources = Vec::new();
    let mut seen_targets = HashSet::new();
    for object in objects {
        let Some(properties) = object
            .pointer("/info/props")
            .and_then(|value| value.as_object())
        else {
            continue;
        };
        let property = |name: &str| {
            properties
                .get(name)
                .and_then(|value| value.as_str())
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(str::to_string)
        };
        if property("media.class").as_deref() != Some("Audio/Source") {
            continue;
        }
        let Some(target) = property("node.name") else {
            continue;
        };
        let description = property("node.description");
        let nick = property("node.nick");
        let card_name = property("api.alsa.card.name").or_else(|| property("alsa.card_name"));
        let mut aliases = [
            card_name.clone(),
            nick.clone(),
            description.clone(),
            Some(target.clone()),
        ]
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
        aliases.dedup();
        if aliases.iter().any(|name| {
            let name = name.to_lowercase();
            name.contains("monitor") || name.contains("loopback")
        }) {
            continue;
        }
        if !seen_targets.insert(target.clone()) {
            continue;
        }
        let stable_name = card_name
            .or_else(|| nick.clone())
            .or_else(|| description.clone())
            .unwrap_or_else(|| target.clone());
        let display_name = description.or(nick).unwrap_or_else(|| stable_name.clone());
        sources.push(PipeWireSource {
            stable_name,
            display_name,
            target,
            aliases,
        });
    }
    sources
}

#[cfg(target_os = "linux")]
fn pipewire_default_properties() -> Vec<String> {
    for attempt in 0..3 {
        match pipewire_command("wpctl")
            .args(["inspect", "@DEFAULT_AUDIO_SOURCE@"])
            .output()
        {
            Ok(output) if output.status.success() => {
                let text = String::from_utf8_lossy(&output.stdout);
                let mut values = Vec::new();
                for property in [
                    "api.alsa.card.name",
                    "alsa.card_name",
                    "node.nick",
                    "node.description",
                    "node.name",
                ] {
                    let prefix = format!("{} =", property);
                    if let Some(value) = text.lines().find_map(|line| {
                        let line = line.trim().trim_start_matches('*').trim();
                        line.strip_prefix(&prefix)
                            .map(|value| value.trim().trim_matches('"').to_string())
                    }) {
                        if !value.is_empty() {
                            values.push(value);
                        }
                    }
                }
                if !values.is_empty() {
                    return values;
                }
            }
            _ => {}
        }
        if attempt < 2 {
            std::thread::sleep(Duration::from_millis(75));
        }
    }
    Vec::new()
}

/// Resolve the desktop's current default capture source. PipeWire exposes a
/// friendly node description and the underlying ALSA card name; CPAL uses the
/// latter, so prefer it when available and fall back to CPAL elsewhere.
pub fn detected_system_default_input_name() -> Option<String> {
    #[cfg(target_os = "linux")]
    {
        if let Some(name) = pipewire_default_properties().into_iter().next() {
            return Some(name);
        }
    }

    cpal::default_host()
        .default_input_device()
        .and_then(|device| device.name().ok())
}

/// Thread-safe wrapper for cpal Stream
/// cpal::Stream doesn't implement Send/Sync, so we need to protect it with a Mutex
/// and only allow access through our controlled methods
#[cfg(target_os = "linux")]
struct PipeWireCapture {
    child: Child,
    reader: Option<JoinHandle<()>>,
}

struct StreamHandle {
    cpal: Option<Stream>,
    #[cfg(target_os = "linux")]
    pipewire: Option<PipeWireCapture>,
}

#[cfg(target_os = "linux")]
fn start_pipewire_capture(
    configured_name: Option<&str>,
    gain: f64,
    frames: Arc<Mutex<Vec<i16>>>,
    is_recording: Arc<AtomicBool>,
    audio_level_callback: Arc<Mutex<Option<Box<dyn Fn(f32) + Send + Sync>>>>,
    audio_data_callback: Arc<Mutex<Option<Box<dyn Fn(&[u8]) + Send + Sync>>>>,
) -> Result<(PipeWireCapture, String), String> {
    let sources = pipewire_sources();
    let default_properties = pipewire_default_properties();
    let selected = if let Some(configured_name) = configured_name {
        sources.iter().find(|source| {
            source
                .aliases
                .iter()
                .any(|alias| device_name_matches(alias, configured_name))
        })
    } else {
        sources.iter().find(|source| {
            source.aliases.iter().any(|alias| {
                default_properties
                    .iter()
                    .any(|detected| device_name_matches(alias, detected))
            })
        })
    };

    if configured_name.is_some() && selected.is_none() {
        return Err(format!(
            "Configured PipeWire audio device '{}' is unavailable",
            configured_name.unwrap_or_default()
        ));
    }

    let target = selected
        .map(|source| source.target.as_str())
        .unwrap_or("@DEFAULT_AUDIO_SOURCE@");
    let display_name = selected
        .map(|source| source.display_name.clone())
        .or_else(|| default_properties.first().cloned())
        .unwrap_or_else(|| "system default".to_string());
    let mut child = pipewire_command("pw-record")
        .args([
            "--target",
            target,
            "--format",
            "s16",
            "--rate",
            "16000",
            "--channels",
            "1",
            "--raw",
            "-",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("Failed to start PipeWire recorder: {error}"))?;
    let mut stdout = child
        .stdout
        .take()
        .ok_or_else(|| "PipeWire recorder has no audio output".to_string())?;
    let reader = std::thread::spawn(move || {
        let mut buffer = [0u8; 4096];
        let mut pending = Vec::with_capacity(4097);
        while is_recording.load(Ordering::SeqCst) {
            let read = match stdout.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(read) => read,
            };
            pending.extend_from_slice(&buffer[..read]);
            let complete = pending.len() / 2 * 2;
            if complete == 0 {
                continue;
            }
            let mut processed = Vec::with_capacity(complete / 2);
            for sample in pending[..complete].chunks_exact(2) {
                let value = i16::from_le_bytes([sample[0], sample[1]]) as f64;
                processed.push((value * gain).clamp(-32768.0, 32767.0) as i16);
            }
            pending.drain(..complete);

            let sum: i64 = processed.iter().map(|sample| (*sample as i64).abs()).sum();
            let level = (sum as f32 / processed.len() as f32 / 32768.0).min(1.0);
            if let Some(ref callback) = *audio_level_callback.lock() {
                callback(level);
            }
            if let Some(ref callback) = *audio_data_callback.lock() {
                let mut pcm = Vec::with_capacity(processed.len() * 2);
                for sample in &processed {
                    pcm.extend_from_slice(&sample.to_le_bytes());
                }
                callback(&pcm);
            }
            frames.lock().extend_from_slice(&processed);
        }
    });

    Ok((
        PipeWireCapture {
            child,
            reader: Some(reader),
        },
        display_name,
    ))
}

/// Streaming area resampler. Each 16 kHz output sample is the weighted mean
/// of the source interval it represents. This provides a small anti-aliasing
/// low-pass filter and, unlike selecting every Nth source sample, keeps its
/// phase continuous across CPAL callback boundaries.
struct AreaResampler {
    output_interval: u64,
    remaining: u64,
    weighted_sum: f64,
    accumulated_weight: u64,
}

impl AreaResampler {
    fn new(input_rate: u32) -> Self {
        // Integer phase units avoid long-term drift for rates such as
        // 44.1 kHz that cannot be represented exactly as a floating ratio.
        let output_interval = input_rate as u64;
        Self {
            output_interval,
            remaining: output_interval,
            weighted_sum: 0.0,
            accumulated_weight: 0,
        }
    }

    fn push(&mut self, sample: f64, output: &mut Vec<i16>, gain: f64) {
        let mut source_weight = SAMPLE_RATE as u64;
        while source_weight > 0 {
            let weight = source_weight.min(self.remaining);
            self.weighted_sum += sample * weight as f64;
            self.accumulated_weight += weight;
            self.remaining -= weight;
            source_weight -= weight;

            if self.remaining == 0 {
                let averaged = self.weighted_sum / self.accumulated_weight.max(1) as f64;
                output.push((averaged * gain).clamp(-32768.0, 32767.0) as i16);
                self.remaining = self.output_interval;
                self.weighted_sum = 0.0;
                self.accumulated_weight = 0;
            }
        }
    }
}

/// Audio recorder using cpal for cross-platform support
pub struct AudioRecorder {
    device: Option<Device>,
    configured_device_index: Option<u32>,
    configured_device_name: Option<String>,
    stream: Mutex<StreamHandle>,
    frames: Arc<Mutex<Vec<i16>>>,
    is_recording: Arc<AtomicBool>,
    gain: f64,
    audio_level_callback: Arc<Mutex<Option<Box<dyn Fn(f32) + Send + Sync>>>>,
    audio_data_callback: Arc<Mutex<Option<Box<dyn Fn(&[u8]) + Send + Sync>>>>,
}

impl AudioRecorder {
    /// Create a new audio recorder
    ///
    /// # Arguments
    /// * `device_index` - Optional index of audio device to use
    /// * `gain` - Audio gain factor (clamped between 0.1 and 5.0)
    ///
    /// # Returns
    /// A new AudioRecorder instance
    pub fn new(device_index: Option<u32>, gain: f64) -> Result<Self, String> {
        Self::new_with_name(device_index, None, gain)
    }

    /// Create a recorder, preferring a stable device name over its volatile
    /// enumeration index. USB and PipeWire device indices can change between
    /// application launches or while an audio service is restarting.
    pub fn new_with_name(
        device_index: Option<u32>,
        device_name: Option<&str>,
        gain: f64,
    ) -> Result<Self, String> {
        let host = cpal::default_host();

        #[cfg(target_os = "linux")]
        let pipewire_available = !pipewire_sources().is_empty();
        #[cfg(not(target_os = "linux"))]
        let pipewire_available = false;

        // Device enumeration can change while a USB microphone is being
        // reconnected. Keep a valid configured device when possible, but do
        // not leave the recorder unusable when the saved index is stale. On
        // Linux, do not enumerate ALSA at all when PipeWire is available:
        // some ALSA drivers keep the enumerated USB PCM open, which prevents
        // the desktop audio server from sharing it with other applications.
        let mut enumerated = if pipewire_available {
            Vec::new()
        } else {
            host.input_devices()
                .map(|devices| devices.collect::<Vec<_>>())
                .unwrap_or_default()
        };
        let configured_device_name = device_name
            .map(str::trim)
            .filter(|name| !name.is_empty())
            .map(str::to_string);
        let named = configured_device_name.as_deref().and_then(|name| {
            enumerated
                .iter()
                .find(|device| device.name().ok().as_deref() == Some(name))
                .cloned()
        });
        let device = if pipewire_available {
            None
        } else if let Some(device) = named {
            Some(device)
        } else if let Some(name) = configured_device_name.as_deref() {
            warn!(
                "Configured audio device '{}' is currently unavailable; keeping it selected for reconnect",
                name
            );
            None
        } else if let Some(index) = device_index {
            let selected = enumerated.get(index as usize).cloned();
            if selected.is_none() {
                warn!(
                    "Configured audio device index {} is currently unavailable",
                    index
                );
            }
            selected
        } else {
            if let Some(default) = host.default_input_device() {
                enumerated.push(default);
            }
            let system_default = detected_system_default_input_name();
            enumerated.sort_by_key(|device| {
                let name = device.name().unwrap_or_default();
                let differs_from_system = system_default
                    .as_deref()
                    .is_none_or(|detected| !device_name_matches(&name, detected));
                (differs_from_system, automatic_device_priority(&name))
            });
            enumerated.into_iter().next()
        };

        let clamped_gain = gain.clamp(0.1, 5.0);
        if pipewire_available {
            info!(
                "Using PipeWire desktop audio capture with gain {}",
                clamped_gain
            );
        } else if device.is_none() {
            warn!("No audio input device found, recording may not work");
        } else if let Ok(device_name) = device.as_ref().unwrap().name() {
            info!(
                "Using audio device: {} with gain {}",
                device_name, clamped_gain
            );
        }

        Ok(Self {
            device,
            configured_device_index: device_index,
            configured_device_name,
            stream: Mutex::new(StreamHandle {
                cpal: None,
                #[cfg(target_os = "linux")]
                pipewire: None,
            }),
            // Pre-allocate with capacity to reduce reallocations during recording
            frames: Arc::new(Mutex::new(Vec::with_capacity(SAMPLE_RATE as usize * 60))), // 1 minute max
            is_recording: Arc::new(AtomicBool::new(false)),
            gain: clamped_gain,
            audio_level_callback: Arc::new(Mutex::new(None)),
            audio_data_callback: Arc::new(Mutex::new(None)),
        })
    }

    /// Get list of available input devices
    ///
    /// # Returns
    /// Vector of tuples containing (device_index, device_name)
    pub fn get_devices() -> Vec<(u32, String)> {
        #[cfg(target_os = "linux")]
        {
            let sources = pipewire_sources();
            if !sources.is_empty() {
                let devices = sources
                    .into_iter()
                    .enumerate()
                    .map(|(index, source)| (index as u32, source.stable_name))
                    .collect::<Vec<_>>();
                debug!("Found {} PipeWire audio input devices", devices.len());
                return devices;
            }
        }

        let host = cpal::default_host();
        let mut devices = Vec::new();
        let mut seen_names = HashSet::new();

        if let Ok(input_devices) = host.input_devices() {
            for (i, device) in input_devices.enumerate() {
                let name = device.name().unwrap_or_else(|_| format!("Device {}", i));
                let normalized = name.trim().to_lowercase();
                let generic = matches!(
                    normalized.as_str(),
                    "default" | "pipewire" | "pulse" | "sysdefault"
                );
                let loopback = normalized.contains("monitor") || normalized.contains("loopback");
                if !generic && !loopback && seen_names.insert(normalized) {
                    devices.push((i as u32, name));
                }
            }
        }

        debug!("Found {} audio input devices", devices.len());
        devices
    }

    /// Set the audio level callback
    pub fn set_audio_level_callback<F>(&mut self, callback: F)
    where
        F: Fn(f32) + Send + Sync + 'static,
    {
        *self.audio_level_callback.lock() = Some(Box::new(callback));
    }

    /// Set the audio data callback for streaming ASR
    pub fn set_audio_data_callback<F>(&mut self, callback: F)
    where
        F: Fn(&[u8]) + Send + Sync + 'static,
    {
        *self.audio_data_callback.lock() = Some(Box::new(callback));
    }

    pub fn clear_audio_data_callback(&mut self) {
        *self.audio_data_callback.lock() = None;
    }

    /// Start recording
    ///
    /// # Returns
    /// Result indicating success or error message
    ///
    /// # Notes
    /// If already recording, this is a no-op and returns Ok(())
    pub fn start(&mut self) -> Result<(), String> {
        if self.is_recording.load(Ordering::SeqCst) {
            debug!("Already recording, ignoring start request");
            return Ok(());
        }

        // Clear previous frames
        self.frames.lock().clear();
        self.is_recording.store(true, Ordering::SeqCst);

        let frames = Arc::clone(&self.frames);
        let is_recording = Arc::clone(&self.is_recording);
        let audio_level_callback = Arc::clone(&self.audio_level_callback);
        let audio_data_callback = Arc::clone(&self.audio_data_callback);
        let gain = self.gain;

        // On Linux, PipeWire is the desktop audio device layer used by apps
        // such as browsers and meeting clients. Recording through it permits
        // concurrent microphone use and keeps USB devices discoverable even
        // while another application has an active capture stream.
        #[cfg(target_os = "linux")]
        {
            match start_pipewire_capture(
                self.configured_device_name.as_deref(),
                gain,
                Arc::clone(&frames),
                Arc::clone(&is_recording),
                Arc::clone(&audio_level_callback),
                Arc::clone(&audio_data_callback),
            ) {
                Ok((mut capture, device_name)) => {
                    // PipeWire may need a few scheduling cycles before the
                    // first audio buffer arrives, especially while another
                    // conferencing app is capturing. A live pw-record child
                    // already means the target was accepted; do not reject a
                    // valid microphone merely because its first frame is a
                    // little later than Speaky's UI startup.
                    std::thread::sleep(Duration::from_millis(80));
                    let exited = capture.child.try_wait().ok().flatten().is_some();
                    if !exited {
                        info!(
                            "Recording started successfully on PipeWire source '{}'",
                            device_name
                        );
                        self.stream.lock().pipewire = Some(capture);
                        return Ok(());
                    }
                    let _ = capture.child.kill();
                    let _ = capture.child.wait();
                    if let Some(reader) = capture.reader.take() {
                        let _ = reader.join();
                    }
                    self.frames.lock().clear();
                    warn!(
                        "PipeWire source '{}' exited during startup; trying native fallback",
                        device_name
                    );
                }
                Err(error) => warn!("PipeWire capture unavailable: {}", error),
            }
        }

        // An explicit selection is strict and is resolved by its stable name
        // on every recording. Automatic mode instead probes all current input
        // devices in reliability order until one actually produces frames.
        let host = cpal::default_host();
        let enumerated = host
            .input_devices()
            .map(|devices| devices.collect::<Vec<_>>())
            .unwrap_or_default();
        let mut candidates = if let Some(configured_name) = self.configured_device_name.as_deref() {
            enumerated
                .into_iter()
                .filter(|device| device.name().ok().as_deref() == Some(configured_name))
                .collect::<Vec<_>>()
        } else if let Some(configured_index) = self.configured_device_index {
            enumerated
                .into_iter()
                .nth(configured_index as usize)
                .into_iter()
                .collect::<Vec<_>>()
        } else {
            let mut automatic_candidates = enumerated;
            if let Some(device) = self.device.take() {
                automatic_candidates.push(device);
            }
            if let Some(default) = host.default_input_device() {
                automatic_candidates.push(default);
            }
            let system_default = detected_system_default_input_name();
            automatic_candidates.sort_by_key(|device| {
                let name = device.name().unwrap_or_default();
                let differs_from_system = system_default
                    .as_deref()
                    .is_none_or(|detected| !device_name_matches(&name, detected));
                (differs_from_system, automatic_device_priority(&name))
            });
            automatic_candidates
        };
        // The same ALSA/PipeWire endpoint can be returned twice (once as the
        // configured handle and once during enumeration). Remove duplicates
        // before trying fallbacks so a short candidate list cannot crowd out
        // the physical microphone.
        let mut seen_names = HashSet::new();
        candidates.retain(|device| {
            let name = device.name().unwrap_or_default();
            seen_names.insert(name)
        });

        if candidates.is_empty() {
            self.is_recording.store(false, Ordering::SeqCst);
            return Err(if let Some(name) = self.configured_device_name.as_deref() {
                format!("Configured audio device '{}' is unavailable", name)
            } else if let Some(index) = self.configured_device_index {
                format!("Configured audio device index {} is unavailable", index)
            } else {
                "No audio input device available".to_string()
            });
        }

        let mut last_error = None;
        for device in candidates {
            let device_name = device
                .name()
                .unwrap_or_else(|_| "unknown device".to_string());
            let supported = match device.default_input_config() {
                Ok(config) => config,
                Err(error) => {
                    warn!("Failed to query audio device '{}': {}", device_name, error);
                    last_error = Some(error.to_string());
                    continue;
                }
            };
            let input_rate = supported.sample_rate().0;
            let input_channels = supported.channels() as usize;
            let stream_config = supported.config();

            let stream = match supported.sample_format() {
                SampleFormat::I16 => build_stream::<i16>(
                    &device,
                    &stream_config,
                    input_rate,
                    input_channels,
                    gain,
                    Arc::clone(&frames),
                    Arc::clone(&is_recording),
                    Arc::clone(&audio_level_callback),
                    Arc::clone(&audio_data_callback),
                    |sample| sample,
                ),
                SampleFormat::F32 => build_stream::<f32>(
                    &device,
                    &stream_config,
                    input_rate,
                    input_channels,
                    gain,
                    Arc::clone(&frames),
                    Arc::clone(&is_recording),
                    Arc::clone(&audio_level_callback),
                    Arc::clone(&audio_data_callback),
                    |sample| (sample.clamp(-1.0, 1.0) * 32767.0) as i16,
                ),
                SampleFormat::U16 => build_stream::<u16>(
                    &device,
                    &stream_config,
                    input_rate,
                    input_channels,
                    gain,
                    Arc::clone(&frames),
                    Arc::clone(&is_recording),
                    Arc::clone(&audio_level_callback),
                    Arc::clone(&audio_data_callback),
                    |sample| (sample as i32 - 32768) as i16,
                ),
                format => Err(format!("unsupported sample format {:?}", format)),
            };

            let stream = match stream {
                Ok(stream) => stream,
                Err(error) => {
                    warn!("Failed to open audio device '{}': {}", device_name, error);
                    last_error = Some(error);
                    continue;
                }
            };

            if let Err(error) = stream.play() {
                warn!("Failed to start audio device '{}': {}", device_name, error);
                last_error = Some(error.to_string());
                continue;
            }

            // Some ALSA devices report a successful stream but immediately
            // fail in their callback (for example a stale PCH timestamp).
            // Give the stream a short moment to produce frames before
            // accepting it, then continue with the next input device.
            std::thread::sleep(Duration::from_millis(150));
            if frames.lock().is_empty() {
                warn!(
                    "Audio device '{}' produced no frames; trying fallback",
                    device_name
                );
                self.is_recording.store(false, Ordering::SeqCst);
                drop(stream);
                self.frames.lock().clear();
                self.is_recording.store(true, Ordering::SeqCst);
                last_error = Some(format!("device '{}' produced no frames", device_name));
                continue;
            }

            info!("Recording started successfully on '{}'", device_name);
            self.device = Some(device);
            self.stream.lock().cpal = Some(stream);
            return Ok(());
        }

        self.is_recording.store(false, Ordering::SeqCst);
        Err(format!(
            "Failed to start any audio input device{}",
            last_error
                .map(|error| format!(": {}", error))
                .unwrap_or_default()
        ))
    }

    /// Stop recording and return WAV data
    ///
    /// # Returns
    /// WAV-encoded audio data as bytes
    ///
    /// # Notes
    /// Returns empty Vec if no audio was captured
    pub fn stop(&mut self) -> Vec<u8> {
        if !self.is_recording.load(Ordering::SeqCst) {
            debug!("Not recording, stop is no-op");
            return Vec::new();
        }

        self.is_recording.store(false, Ordering::SeqCst);

        #[cfg(target_os = "linux")]
        if let Some(mut capture) = self.stream.lock().pipewire.take() {
            let _ = capture.child.kill();
            let _ = capture.child.wait();
            if let Some(reader) = capture.reader.take() {
                let _ = reader.join();
            }
        }

        if let Some(stream) = self.stream.lock().cpal.take() {
            drop(stream);
        }

        let frames = self.frames.lock().clone();
        if frames.is_empty() {
            info!("Recording stopped, no frames captured");
            return Vec::new();
        }

        let wav_data = self.create_wav(&frames);
        info!(
            "Recording stopped: {} frames, {} bytes WAV",
            frames.len(),
            wav_data.len()
        );
        wav_data
    }

    /// Check if currently recording
    ///
    /// # Returns
    /// true if recording, false otherwise
    pub fn is_recording(&self) -> bool {
        self.is_recording.load(Ordering::SeqCst)
    }

    /// Get current audio level (0.0 - 1.0)
    pub fn get_audio_level(&self) -> f32 {
        let frames = self.frames.lock();
        if frames.is_empty() {
            return 0.0;
        }

        // Get last 1024 samples
        let start = frames.len().saturating_sub(1024);
        let samples = &frames[start..];

        let sum: i64 = samples.iter().map(|&s| (s as i64).abs()).sum();
        let avg = sum as f32 / samples.len() as f32;
        (avg / 32768.0).min(1.0)
    }

    /// Get raw PCM data (for streaming)
    pub fn get_pcm_data(&self) -> Vec<u8> {
        let frames = self.frames.lock();
        let mut data = Vec::with_capacity(frames.len() * 2);
        for sample in frames.iter() {
            data.extend_from_slice(&sample.to_le_bytes());
        }
        data
    }

    /// Create WAV file from samples
    fn create_wav(&self, samples: &[i16]) -> Vec<u8> {
        let data_len = samples.len() * 2;
        let file_len = 36 + data_len;

        let mut buffer = Vec::with_capacity(44 + data_len);

        // RIFF header
        buffer.extend_from_slice(b"RIFF");
        buffer.extend_from_slice(&(file_len as u32).to_le_bytes());
        buffer.extend_from_slice(b"WAVE");

        // fmt subchunk
        buffer.extend_from_slice(b"fmt ");
        buffer.extend_from_slice(&16u32.to_le_bytes()); // Subchunk1Size
        buffer.extend_from_slice(&1u16.to_le_bytes()); // AudioFormat (PCM)
        buffer.extend_from_slice(&CHANNELS.to_le_bytes()); // NumChannels
        buffer.extend_from_slice(&SAMPLE_RATE.to_le_bytes()); // SampleRate
        let byte_rate = SAMPLE_RATE * CHANNELS as u32 * SAMPLE_WIDTH as u32;
        buffer.extend_from_slice(&byte_rate.to_le_bytes()); // ByteRate
        let block_align = CHANNELS * SAMPLE_WIDTH;
        buffer.extend_from_slice(&block_align.to_le_bytes()); // BlockAlign
        let bits_per_sample = SAMPLE_WIDTH * 8;
        buffer.extend_from_slice(&bits_per_sample.to_le_bytes()); // BitsPerSample

        // data subchunk
        buffer.extend_from_slice(b"data");
        buffer.extend_from_slice(&(data_len as u32).to_le_bytes());

        for sample in samples {
            buffer.extend_from_slice(&sample.to_le_bytes());
        }

        buffer
    }
}

/// Build a capture stream for one of cpal's supported sample formats. Audio
/// devices commonly expose 48 kHz (and sometimes float samples), while ASR
/// engines expect 16 kHz mono PCM. The callback converts, mixes down and
/// performs a lightweight resampling before storing samples.
fn build_stream<T>(
    device: &Device,
    config: &StreamConfig,
    input_rate: u32,
    input_channels: usize,
    gain: f64,
    frames: Arc<Mutex<Vec<i16>>>,
    is_recording: Arc<AtomicBool>,
    audio_level_callback: Arc<Mutex<Option<Box<dyn Fn(f32) + Send + Sync>>>>,
    audio_data_callback: Arc<Mutex<Option<Box<dyn Fn(&[u8]) + Send + Sync>>>>,
    converter: fn(T) -> i16,
) -> Result<Stream, String>
where
    T: cpal::SizedSample + 'static,
{
    if input_channels == 0 || input_rate == 0 {
        return Err("invalid audio device format".to_string());
    }

    let resampler = Arc::new(Mutex::new(AreaResampler::new(input_rate)));
    let stream = device
        .build_input_stream(
            config,
            move |data: &[T], _: &cpal::InputCallbackInfo| {
                if !is_recording.load(Ordering::SeqCst) {
                    return;
                }

                let mut resampler = resampler.lock();
                let mut processed = Vec::new();

                for frame in data.chunks(input_channels) {
                    if frame.is_empty() {
                        continue;
                    }

                    let sum: i64 = frame.iter().map(|&sample| converter(sample) as i64).sum();
                    let mono = sum as f64 / frame.len() as f64;
                    resampler.push(mono, &mut processed, gain);
                }
                if processed.is_empty() {
                    return;
                }

                let sum: i64 = processed.iter().map(|&sample| (sample as i64).abs()).sum();
                let average = sum as f32 / processed.len() as f32;
                let level = (average / 32768.0).min(1.0);
                if let Some(ref callback) = *audio_level_callback.lock() {
                    callback(level);
                }
                if let Some(ref callback) = *audio_data_callback.lock() {
                    let mut pcm = Vec::with_capacity(processed.len() * 2);
                    for sample in &processed {
                        pcm.extend_from_slice(&sample.to_le_bytes());
                    }
                    callback(&pcm);
                }
                frames.lock().extend_from_slice(&processed);
            },
            move |error| {
                error!("Audio stream error: {:?}", error);
            },
            None,
        )
        .map_err(|error| error.to_string())?;

    Ok(stream)
}

impl Drop for AudioRecorder {
    fn drop(&mut self) {
        self.is_recording.store(false, Ordering::SeqCst);
        #[cfg(target_os = "linux")]
        if let Some(mut capture) = self.stream.lock().pipewire.take() {
            let _ = capture.child.kill();
            let _ = capture.child.wait();
            if let Some(reader) = capture.reader.take() {
                let _ = reader.join();
            }
        }
        self.stream.lock().cpal.take();
    }
}

#[cfg(test)]
mod tests {
    use super::{automatic_device_priority, AreaResampler};

    #[test]
    fn automatic_selection_prefers_physical_usb_microphones() {
        let mut names = [
            "default",
            "pipewire",
            "Monitor of Output",
            "AB13X USB Audio",
        ];
        names.sort_by_key(|name| automatic_device_priority(name));
        assert_eq!(names[0], "AB13X USB Audio");
        assert_eq!(names[3], "Monitor of Output");
    }

    #[test]
    fn resamples_48khz_to_16khz_without_changing_a_constant_signal() {
        let mut resampler = AreaResampler::new(48_000);
        let mut output = Vec::new();
        for _ in 0..48_000 {
            resampler.push(1_000.0, &mut output, 1.0);
        }

        assert_eq!(output.len(), 16_000);
        assert!(output.iter().all(|sample| *sample == 1_000));
    }

    #[test]
    fn keeps_resampling_state_continuous_across_input_chunks() {
        let input = (0..44_100)
            .map(|index| ((index % 997) as i16) - 498)
            .collect::<Vec<_>>();
        let mut whole = AreaResampler::new(44_100);
        let mut chunked = AreaResampler::new(44_100);
        let mut whole_output = Vec::new();
        let mut chunked_output = Vec::new();

        for sample in &input {
            whole.push(*sample as f64, &mut whole_output, 1.0);
        }
        for chunk in input.chunks(317) {
            for sample in chunk {
                chunked.push(*sample as f64, &mut chunked_output, 1.0);
            }
        }

        assert_eq!(whole_output.len(), 16_000);
        assert_eq!(chunked_output, whole_output);
    }
}

// Make AudioRecorder thread-safe by using Arc<Mutex<>> internally
unsafe impl Send for AudioRecorder {}
unsafe impl Sync for AudioRecorder {}
