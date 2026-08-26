use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, SampleFormat, Stream, StreamConfig};
use log::{debug, error, info, warn};
use parking_lot::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

/// Audio format constants
const SAMPLE_RATE: u32 = 16000;
const CHANNELS: u16 = 1;
const SAMPLE_WIDTH: u16 = 2; // 16-bit

/// Thread-safe wrapper for cpal Stream
/// cpal::Stream doesn't implement Send/Sync, so we need to protect it with a Mutex
/// and only allow access through our controlled methods
struct StreamHandle(Option<Stream>);

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
    device_index: Option<u32>,
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
        let host = cpal::default_host();

        // Device enumeration can change while a USB microphone is being
        // reconnected. Keep a valid configured device when possible, but do
        // not leave the recorder unusable when the saved index is stale.
        let mut enumerated = host
            .input_devices()
            .map(|devices| devices.collect::<Vec<_>>())
            .unwrap_or_default();
        let device = if let Some(index) = device_index {
            let selected = enumerated.get(index as usize).cloned();
            if selected.is_none() {
                warn!(
                    "Configured audio device index {} is unavailable; falling back to the default input",
                    index
                );
            }
            selected
                .or_else(|| host.default_input_device())
                .or_else(|| enumerated.pop())
        } else {
            host.default_input_device().or_else(|| enumerated.pop())
        };

        let clamped_gain = gain.clamp(0.1, 5.0);
        if device.is_none() {
            warn!("No audio input device found, recording may not work");
        } else if let Ok(device_name) = device.as_ref().unwrap().name() {
            info!(
                "Using audio device: {} with gain {}",
                device_name, clamped_gain
            );
        }

        Ok(Self {
            device,
            device_index,
            stream: Mutex::new(StreamHandle(None)),
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
        let host = cpal::default_host();
        let mut devices = Vec::new();

        if let Ok(input_devices) = host.input_devices() {
            for (i, device) in input_devices.enumerate() {
                let name = device.name().unwrap_or_else(|_| format!("Device {}", i));
                devices.push((i as u32, name));
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

        // Prefer the configured/default device, but fall back to another
        // capture device when the system default points at an unavailable
        // PipeWire/PulseAudio endpoint (common on minimal Linux setups).
        let mut candidates = Vec::new();
        if let Some(device) = self.device.take() {
            candidates.push(device);
        }
        if self.device_index.is_none() {
            if let Ok(devices) = cpal::default_host().input_devices() {
                candidates.extend(devices);
            }
        }

        // On Linux, PipeWire/ALSA may expose a virtual "default" endpoint
        // before the physical USB microphone. Try named devices first so a
        // stale default cannot block the streaming session.
        candidates.sort_by_key(|device| {
            device
                .name()
                .map(|name| name.eq_ignore_ascii_case("default"))
                .unwrap_or(false)
        });
        candidates.truncate(8);

        if candidates.is_empty() {
            self.is_recording.store(false, Ordering::SeqCst);
            return Err("No audio input device available".to_string());
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
            self.stream.lock().0 = Some(stream);
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

        if let Some(stream) = self.stream.lock().0.take() {
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
        self.stream.lock().0.take();
    }
}

#[cfg(test)]
mod tests {
    use super::AreaResampler;

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
