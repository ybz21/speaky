use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, SampleRate, Stream, StreamConfig};
use log::{error, info, warn};
use parking_lot::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// Audio format constants
const SAMPLE_RATE: u32 = 16000;
const CHANNELS: u16 = 1;
const SAMPLE_WIDTH: u16 = 2; // 16-bit

/// Audio recorder using cpal for cross-platform support
pub struct AudioRecorder {
    device: Option<Device>,
    stream: Option<Stream>,
    frames: Arc<Mutex<Vec<i16>>>,
    is_recording: Arc<AtomicBool>,
    gain: f64,
    audio_level_callback: Option<Box<dyn Fn(f32) + Send + Sync>>,
    audio_data_callback: Option<Box<dyn Fn(&[u8]) + Send + Sync>>,
}

impl AudioRecorder {
    /// Create a new audio recorder
    pub fn new(device_index: Option<u32>, gain: f64) -> Self {
        let host = cpal::default_host();

        let device = if let Some(index) = device_index {
            host.input_devices()
                .ok()
                .and_then(|mut devices| devices.nth(index as usize))
        } else {
            host.default_input_device()
        };

        if device.is_none() {
            warn!("No audio input device found");
        } else {
            info!(
                "Audio device: {:?}",
                device.as_ref().and_then(|d| d.name().ok())
            );
        }

        Self {
            device,
            stream: None,
            frames: Arc::new(Mutex::new(Vec::new())),
            is_recording: Arc::new(AtomicBool::new(false)),
            gain: gain.clamp(0.1, 5.0),
            audio_level_callback: None,
            audio_data_callback: None,
        }
    }

    /// Get list of available input devices
    pub fn get_devices() -> Vec<(u32, String)> {
        let host = cpal::default_host();
        let mut devices = Vec::new();

        if let Ok(input_devices) = host.input_devices() {
            for (i, device) in input_devices.enumerate() {
                let name = device.name().unwrap_or_else(|_| format!("Device {}", i));
                devices.push((i as u32, name));
            }
        }

        devices
    }

    /// Set the audio level callback
    pub fn set_audio_level_callback<F>(&mut self, callback: F)
    where
        F: Fn(f32) + Send + Sync + 'static,
    {
        self.audio_level_callback = Some(Box::new(callback));
    }

    /// Set the audio data callback for streaming ASR
    pub fn set_audio_data_callback<F>(&mut self, callback: F)
    where
        F: Fn(&[u8]) + Send + Sync + 'static,
    {
        self.audio_data_callback = Some(Box::new(callback));
    }

    /// Start recording
    pub fn start(&mut self) -> Result<(), String> {
        if self.is_recording.load(Ordering::SeqCst) {
            return Ok(());
        }

        let device = self
            .device
            .as_ref()
            .ok_or_else(|| "No audio device available".to_string())?;

        let config = StreamConfig {
            channels: CHANNELS,
            sample_rate: SampleRate(SAMPLE_RATE),
            buffer_size: cpal::BufferSize::Default,
        };

        // Clear previous frames
        self.frames.lock().clear();
        self.is_recording.store(true, Ordering::SeqCst);

        let frames = Arc::clone(&self.frames);
        let is_recording = Arc::clone(&self.is_recording);
        let gain = self.gain;

        // Build stream with i16 samples
        let stream = device
            .build_input_stream(
                &config,
                move |data: &[i16], _: &cpal::InputCallbackInfo| {
                    if !is_recording.load(Ordering::SeqCst) {
                        return;
                    }

                    // Apply gain
                    let processed: Vec<i16> = data
                        .iter()
                        .map(|&s| {
                            let sample = (s as f64 * gain) as i32;
                            sample.clamp(-32768, 32767) as i16
                        })
                        .collect();

                    frames.lock().extend_from_slice(&processed);
                },
                move |err| {
                    error!("Audio stream error: {:?}", err);
                },
                None,
            )
            .map_err(|e| format!("Failed to build stream: {}", e))?;

        stream.play().map_err(|e| format!("Failed to play stream: {}", e))?;
        self.stream = Some(stream);

        info!("Recording started");
        Ok(())
    }

    /// Stop recording and return WAV data
    pub fn stop(&mut self) -> Vec<u8> {
        self.is_recording.store(false, Ordering::SeqCst);

        if let Some(stream) = self.stream.take() {
            drop(stream);
        }

        let frames = self.frames.lock().clone();
        if frames.is_empty() {
            info!("Recording stopped, no frames captured");
            return Vec::new();
        }

        let wav_data = self.create_wav(&frames);
        info!(
            "Recording stopped, {} frames, {} bytes WAV",
            frames.len(),
            wav_data.len()
        );
        wav_data
    }

    /// Check if currently recording
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

impl Drop for AudioRecorder {
    fn drop(&mut self) {
        self.is_recording.store(false, Ordering::SeqCst);
        self.stream.take();
    }
}

// AudioRecorder is Send + Sync because all its fields are thread-safe
unsafe impl Send for AudioRecorder {}
unsafe impl Sync for AudioRecorder {}
