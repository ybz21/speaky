use super::{Engine, EngineError, EngineResult};
use byteorder::{BigEndian, WriteBytesExt};
use flate2::write::GzEncoder;
use flate2::Compression;
use futures_util::{SinkExt, StreamExt};
use log::{debug, error, info};
use once_cell::sync::Lazy;
use std::io::Write;
use std::sync::{
    mpsc::{self, Receiver},
    Mutex,
};
use std::time::Duration;
use tokio::runtime::Runtime;
use tokio_tungstenite::{
    connect_async,
    tungstenite::{http::Request, Message},
};
use uuid::Uuid;

/// Global Tokio runtime for WebSocket connections
/// Using a static runtime avoids creating a new runtime for each transcription
static RUNTIME: Lazy<Runtime> = Lazy::new(|| {
    tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .thread_name("speaky-ws")
        .worker_threads(2)
        .build()
        .expect("Failed to create Tokio runtime")
});

// Protocol constants
const PROTOCOL_VERSION: u8 = 0b0001;
const MESSAGE_TYPE_FULL_REQUEST: u8 = 0b0001;
const MESSAGE_TYPE_AUDIO_ONLY: u8 = 0b0010;
const WS_CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
const WS_RESPONSE_TIMEOUT: Duration = Duration::from_secs(15);
const MESSAGE_TYPE_FULL_RESPONSE: u8 = 0b1001;
const MESSAGE_TYPE_ERROR_RESPONSE: u8 = 0b1111;
const FLAGS_POS_SEQUENCE: u8 = 0b0001;
const FLAGS_NEG_WITH_SEQUENCE: u8 = 0b0011;
const SERIALIZATION_JSON: u8 = 0b0001;
const COMPRESSION_GZIP: u8 = 0b0001;
const FINAL_WS_URL: &str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream";

/// Volcengine BigModel ASR engine
#[derive(Clone)]
pub struct VolcBigModelEngine {
    api_key: String,
    app_key: String,
    access_key: String,
    resource_id: String,
    ws_url: String,
    segment_duration_ms: u32,
}

impl VolcBigModelEngine {
    pub fn new(api_key: &str, app_key: &str, access_key: &str, resource_id: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            app_key: app_key.to_string(),
            access_key: access_key.to_string(),
            resource_id: if resource_id.is_empty() {
                "volc.bigasr.sauc.duration".to_string()
            } else {
                resource_id.to_string()
            },
            ws_url: "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async".to_string(),
            segment_duration_ms: 200,
        }
    }

    fn build_header(message_type: u8, flags: u8, serialization: u8, compression: u8) -> Vec<u8> {
        vec![
            (PROTOCOL_VERSION << 4) | 1, // version + header size
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0x00, // reserved
        ]
    }

    fn build_full_request(&self, seq: i32, sample_rate: u32, audio_format: &str) -> Vec<u8> {
        let header = Self::build_header(
            MESSAGE_TYPE_FULL_REQUEST,
            FLAGS_POS_SEQUENCE,
            SERIALIZATION_JSON,
            COMPRESSION_GZIP,
        );

        let payload = serde_json::json!({
            "user": {"uid": "speaky"},
            "audio": {
                "format": audio_format,
                "codec": "raw",
                "rate": sample_rate,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": true,
                "enable_punc": true,
                "enable_ddc": true,
                "show_utterances": true,
                "enable_nonstream": false,
            },
        });

        let payload_json = payload.to_string();
        let payload_compressed = gzip_compress(payload_json.as_bytes());

        let mut request = header;
        request.write_i32::<BigEndian>(seq).unwrap();
        request
            .write_u32::<BigEndian>(payload_compressed.len() as u32)
            .unwrap();
        request.extend_from_slice(&payload_compressed);

        request
    }

    fn build_audio_request(&self, seq: i32, audio_data: &[u8], is_last: bool) -> Vec<u8> {
        let (flags, actual_seq) = if is_last {
            (FLAGS_NEG_WITH_SEQUENCE, -seq)
        } else {
            (FLAGS_POS_SEQUENCE, seq)
        };

        let header = Self::build_header(
            MESSAGE_TYPE_AUDIO_ONLY,
            flags,
            SERIALIZATION_JSON,
            COMPRESSION_GZIP,
        );

        let compressed = gzip_compress(audio_data);

        let mut request = header;
        request.write_i32::<BigEndian>(actual_seq).unwrap();
        request
            .write_u32::<BigEndian>(compressed.len() as u32)
            .unwrap();
        request.extend_from_slice(&compressed);

        request
    }

    fn parse_response(data: &[u8]) -> ParsedResponse {
        let mut result = ParsedResponse::default();

        if data.len() < 4 {
            return result;
        }

        let header_size = (data[0] & 0x0f) as usize;
        let message_type = data[1] >> 4;
        let flags = data[1] & 0x0f;
        let compression = data[2] & 0x0f;

        let mut payload = &data[header_size * 4..];

        // Parse sequence if present
        if flags & 0x01 != 0 && payload.len() >= 4 {
            result.sequence = i32::from_be_bytes([payload[0], payload[1], payload[2], payload[3]]);
            payload = &payload[4..];
        }

        // Check for last flag
        if flags & 0x02 != 0 {
            result.is_last = true;
        }

        // Parse message type
        if message_type == MESSAGE_TYPE_FULL_RESPONSE && payload.len() >= 4 {
            let _payload_size =
                u32::from_be_bytes([payload[0], payload[1], payload[2], payload[3]]);
            payload = &payload[4..];
        } else if message_type == MESSAGE_TYPE_ERROR_RESPONSE && payload.len() >= 8 {
            result.code = i32::from_be_bytes([payload[0], payload[1], payload[2], payload[3]]);
            let _payload_size =
                u32::from_be_bytes([payload[4], payload[5], payload[6], payload[7]]);
            payload = &payload[8..];
        }

        if payload.is_empty() {
            return result;
        }

        // Decompress if needed
        let decompressed = if compression == COMPRESSION_GZIP {
            match gzip_decompress(payload) {
                Ok(data) => data,
                Err(e) => {
                    error!("Failed to decompress: {}", e);
                    return result;
                }
            }
        } else {
            payload.to_vec()
        };

        // Parse JSON
        if let Ok(json) = serde_json::from_slice::<serde_json::Value>(&decompressed) {
            result.payload = Some(json);
        }

        result
    }

    async fn transcribe_async(
        &self,
        audio_data: &[u8],
        _language: &str,
        partial_callback: Option<super::PartialResultCallback>,
        ws_url: &str,
        pace_audio: bool,
    ) -> Result<String, String> {
        let request_id = Uuid::new_v4().to_string();
        info!("Starting BigModel transcription, request_id={}", request_id);

        // Parse WAV to get sample rate
        let sample_rate = parse_wav_sample_rate(audio_data).unwrap_or(16000);
        info!("Audio sample rate: {}", sample_rate);

        // Build WebSocket request with custom headers
        let mut request_builder = Request::builder()
            .uri(ws_url)
            .header("X-Api-Resource-Id", &self.resource_id)
            .header("X-Api-Request-Id", &request_id)
            .header("Host", "openspeech.bytedance.com")
            .header("Upgrade", "websocket")
            .header("Connection", "Upgrade")
            .header(
                "Sec-WebSocket-Key",
                tokio_tungstenite::tungstenite::handshake::client::generate_key(),
            )
            .header("Sec-WebSocket-Version", "13");

        if !self.api_key.is_empty() {
            request_builder = request_builder.header("X-Api-Key", &self.api_key);
        } else {
            request_builder = request_builder
                .header("X-Api-Access-Key", &self.access_key)
                .header("X-Api-App-Key", &self.app_key);
        }

        let request = request_builder
            .body(())
            .map_err(|e: tokio_tungstenite::tungstenite::http::Error| e.to_string())?;

        let (mut ws, _) = tokio::time::timeout(WS_CONNECT_TIMEOUT, connect_async(request))
            .await
            .map_err(|_| "WebSocket connection timed out".to_string())?
            .map_err(|e| format!("Failed to connect: {}", e))?;

        info!("Connected to WebSocket");

        // Send full request
        let full_request = self.build_full_request(1, sample_rate, "wav");
        ws.send(Message::Binary(full_request.into()))
            .await
            .map_err(|e| format!("Failed to send full request: {}", e))?;

        // Wait for initial response
        let initial_message = tokio::time::timeout(WS_RESPONSE_TIMEOUT, ws.next())
            .await
            .map_err(|_| "Initial recognition response timed out".to_string())?;
        if let Some(msg) = initial_message {
            let msg = msg.map_err(|e| format!("Failed to receive: {}", e))?;
            if let Message::Binary(data) = msg {
                let resp = Self::parse_response(&data);
                if resp.code != 0 {
                    return Err(format!("Initial request failed: code={}", resp.code));
                }
                debug!("Initial response received");
            }
        }

        // Send audio in segments
        let segment_size = (sample_rate * 2 * self.segment_duration_ms / 1000) as usize;
        let segments: Vec<_> = audio_data.chunks(segment_size).collect();
        let total_segments = segments.len();

        let mut seq = 2;
        for (i, segment) in segments.iter().enumerate() {
            let is_last = i == total_segments - 1;
            let audio_request = self.build_audio_request(seq, segment, is_last);
            ws.send(Message::Binary(audio_request.into()))
                .await
                .map_err(|e| format!("Failed to send audio: {}", e))?;

            debug!(
                "Sent segment {}/{}, last={}",
                i + 1,
                total_segments,
                is_last
            );

            if !is_last {
                seq += 1;
                if pace_audio {
                    tokio::time::sleep(tokio::time::Duration::from_millis(
                        self.segment_duration_ms as u64,
                    ))
                    .await;
                }
            }
        }

        // Receive responses
        let mut result_text = String::new();

        loop {
            let next_message = tokio::time::timeout(WS_RESPONSE_TIMEOUT, ws.next())
                .await
                .map_err(|_| "Recognition response timed out".to_string())?;
            let Some(msg) = next_message else {
                break;
            };
            let msg = msg.map_err(|e| format!("Failed to receive: {}", e))?;

            if let Message::Binary(data) = msg {
                let resp = Self::parse_response(&data);
                debug!(
                    "Response: seq={}, last={}, code={}",
                    resp.sequence, resp.is_last, resp.code
                );

                if resp.code != 0 {
                    return Err(format!("Error response: code={}", resp.code));
                }

                if let Some(payload) = &resp.payload {
                    if let Some(result) = payload.get("result") {
                        let mut new_text = None;
                        if let Some(arr) = result.as_array() {
                            if let Some(first) = arr.first() {
                                if let Some(text) = first.get("text").and_then(|t| t.as_str()) {
                                    new_text = Some(text.to_string());
                                }
                            }
                        } else if let Some(text) = result.get("text").and_then(|t| t.as_str()) {
                            new_text = Some(text.to_string());
                        }

                        if let Some(text) = new_text {
                            result_text = text.clone();
                            // Emit partial result if callback is provided
                            if let Some(ref callback) = partial_callback {
                                if !text.is_empty() {
                                    callback(&text);
                                }
                            }
                        }
                    }
                }

                if resp.is_last {
                    info!("Received last response");
                    break;
                }
            }
        }

        let _ = ws.close(None).await;
        info!("Transcription complete: {}", result_text);
        Ok(result_text.trim().to_string())
    }

    /// Run the recorded utterance through the non-streaming endpoint for the
    /// final paste. Realtime recognition still drives the live captions; this
    /// second pass only replaces its lower-accuracy final hypothesis.
    pub fn transcribe_final(&self, audio_data: &[u8], language: &str) -> EngineResult {
        RUNTIME
            .block_on(self.transcribe_async(audio_data, language, None, FINAL_WS_URL, false))
            .map_err(EngineError::NetworkError)
    }

    /// Start a WebSocket session immediately and accept 16 kHz mono PCM as it
    /// arrives from the recorder. This is the path used while the hotkey is
    /// still held, so partial text can be displayed during speech.
    pub fn start_realtime(
        self,
        partial_callback: super::PartialResultCallback,
    ) -> VolcRealtimeSession {
        let (audio_tx, audio_rx) = tokio::sync::mpsc::unbounded_channel();
        let (result_tx, result_rx) = mpsc::channel();

        RUNTIME.spawn(async move {
            let result = self
                .realtime_loop(audio_rx, partial_callback)
                .await
                .map_err(EngineError::NetworkError);
            let _ = result_tx.send(result);
        });

        VolcRealtimeSession {
            audio_tx,
            result_rx: Mutex::new(result_rx),
        }
    }

    async fn realtime_loop(
        &self,
        mut audio_rx: tokio::sync::mpsc::UnboundedReceiver<Option<Vec<u8>>>,
        partial_callback: super::PartialResultCallback,
    ) -> Result<String, String> {
        let request_id = Uuid::new_v4().to_string();
        info!(
            "Starting realtime BigModel session, request_id={}",
            request_id
        );

        let mut request_builder = Request::builder()
            .uri(&self.ws_url)
            .header("X-Api-Resource-Id", &self.resource_id)
            .header("X-Api-Request-Id", &request_id)
            .header("Host", "openspeech.bytedance.com")
            .header("Upgrade", "websocket")
            .header("Connection", "Upgrade")
            .header(
                "Sec-WebSocket-Key",
                tokio_tungstenite::tungstenite::handshake::client::generate_key(),
            )
            .header("Sec-WebSocket-Version", "13");

        if !self.api_key.is_empty() {
            request_builder = request_builder.header("X-Api-Key", &self.api_key);
        } else {
            request_builder = request_builder
                .header("X-Api-Access-Key", &self.access_key)
                .header("X-Api-App-Key", &self.app_key);
        }

        let request = request_builder
            .body(())
            .map_err(|error: tokio_tungstenite::tungstenite::http::Error| error.to_string())?;
        let (mut ws, _) = tokio::time::timeout(WS_CONNECT_TIMEOUT, connect_async(request))
            .await
            .map_err(|_| "Realtime WebSocket connection timed out".to_string())?
            .map_err(|error| format!("Failed to connect: {}", error))?;

        ws.send(Message::Binary(
            self.build_full_request(1, 16000, "pcm").into(),
        ))
        .await
        .map_err(|error| format!("Failed to send initial request: {}", error))?;

        let initial_message = tokio::time::timeout(WS_RESPONSE_TIMEOUT, ws.next())
            .await
            .map_err(|_| "Realtime initial response timed out".to_string())?;
        match initial_message {
            Some(Ok(Message::Binary(data))) => {
                let response = Self::parse_response(&data);
                if response.code != 0 {
                    return Err(format!("Initial request failed: code={}", response.code));
                }
            }
            Some(Ok(_)) => {}
            Some(Err(error)) => return Err(format!("Initial response failed: {}", error)),
            None => return Err("Connection closed before initial response".to_string()),
        }

        info!("Realtime BigModel session ready");
        const PACKET_BYTES: usize = 16000 * 2 * 200 / 1000;
        let mut buffer = Vec::new();
        let mut sequence = 2;
        let mut input_finished = false;
        let mut result_text = String::new();

        loop {
            tokio::select! {
                chunk = audio_rx.recv(), if !input_finished => {
                    match chunk {
                        Some(Some(data)) => {
                            buffer.extend_from_slice(&data);
                            while buffer.len() >= PACKET_BYTES {
                                let remainder = buffer.split_off(PACKET_BYTES);
                                let packet = std::mem::replace(&mut buffer, remainder);
                                ws.send(Message::Binary(
                                    self.build_audio_request(sequence, &packet, false).into()
                                )).await.map_err(|error| format!("Failed to send audio: {}", error))?;
                                sequence += 1;
                            }
                        }
                        Some(None) | None => {
                            ws.send(Message::Binary(
                                self.build_audio_request(sequence, &buffer, true).into()
                            )).await.map_err(|error| format!("Failed to finish audio: {}", error))?;
                            buffer.clear();
                            input_finished = true;
                            info!("Realtime audio input finished");
                        }
                    }
                }
                message = ws.next() => {
                    match message {
                        Some(Ok(Message::Binary(data))) => {
                            let response = Self::parse_response(&data);
                            if response.code != 0 {
                                return Err(format!("ASR response error: code={}", response.code));
                            }
                            if let Some(payload) = &response.payload {
                                if let Some(text) = extract_result_text(payload) {
                                    if !text.is_empty() && text != result_text {
                                        result_text = text;
                                        partial_callback(&result_text);
                                    }
                                }
                            }
                            if response.is_last {
                                info!("Realtime transcription complete: {}", result_text);
                                let _ = ws.close(None).await;
                                return Ok(result_text.trim().to_string());
                            }
                        }
                        Some(Ok(Message::Close(_))) | None => {
                            if input_finished {
                                return Ok(result_text.trim().to_string());
                            }
                            return Err("Realtime WebSocket closed unexpectedly".to_string());
                        }
                        Some(Ok(_)) => {}
                        Some(Err(error)) => return Err(format!("Realtime receive failed: {}", error)),
                    }
                }
                _ = tokio::time::sleep(WS_RESPONSE_TIMEOUT), if input_finished => {
                    return Err("Realtime recognition response timed out".to_string());
                }
            }
        }
    }
}

pub struct VolcRealtimeSession {
    audio_tx: tokio::sync::mpsc::UnboundedSender<Option<Vec<u8>>>,
    result_rx: Mutex<Receiver<EngineResult>>,
}

#[derive(Clone)]
pub struct VolcRealtimeAudioSender {
    audio_tx: tokio::sync::mpsc::UnboundedSender<Option<Vec<u8>>>,
}

impl VolcRealtimeAudioSender {
    pub fn send(&self, audio: &[u8]) {
        let _ = self.audio_tx.send(Some(audio.to_vec()));
    }
}

impl VolcRealtimeSession {
    pub fn audio_sender(&self) -> VolcRealtimeAudioSender {
        VolcRealtimeAudioSender {
            audio_tx: self.audio_tx.clone(),
        }
    }

    pub fn finish(self) -> EngineResult {
        let _ = self.audio_tx.send(None);
        self.result_rx
            .into_inner()
            .unwrap()
            .recv_timeout(Duration::from_secs(10))
            .unwrap_or_else(|error| {
                Err(EngineError::NetworkError(format!(
                    "Realtime recognition timed out: {}",
                    error
                )))
            })
    }
}

impl Engine for VolcBigModelEngine {
    fn name(&self) -> &str {
        "Volcengine BigModel"
    }

    fn is_available(&self) -> bool {
        !self.api_key.is_empty() || (!self.app_key.is_empty() && !self.access_key.is_empty())
    }

    fn transcribe(&self, audio_data: &[u8], language: &str) -> EngineResult {
        // Use global runtime instead of creating a new one each time
        RUNTIME
            .block_on(self.transcribe_async(audio_data, language, None, &self.ws_url, true))
            .map_err(EngineError::NetworkError)
    }

    fn transcribe_with_callback(
        &self,
        audio_data: &[u8],
        language: &str,
        callback: super::PartialResultCallback,
    ) -> EngineResult {
        // Use global runtime instead of creating a new one each time
        RUNTIME
            .block_on(self.transcribe_async(
                audio_data,
                language,
                Some(callback),
                &self.ws_url,
                true,
            ))
            .map_err(EngineError::NetworkError)
    }

    fn supports_streaming(&self) -> bool {
        true
    }
}

#[derive(Default)]
struct ParsedResponse {
    code: i32,
    is_last: bool,
    sequence: i32,
    payload: Option<serde_json::Value>,
}

fn extract_result_text(payload: &serde_json::Value) -> Option<String> {
    let result = payload.get("result")?;
    if let Some(items) = result.as_array() {
        items
            .first()
            .and_then(|item| item.get("text"))
            .and_then(|text| text.as_str())
            .map(str::to_string)
    } else {
        result
            .get("text")
            .and_then(|text| text.as_str())
            .map(str::to_string)
    }
}

fn gzip_compress(data: &[u8]) -> Vec<u8> {
    let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
    encoder.write_all(data).unwrap();
    encoder.finish().unwrap()
}

fn gzip_decompress(data: &[u8]) -> Result<Vec<u8>, std::io::Error> {
    use flate2::read::GzDecoder;
    use std::io::Read;

    let mut decoder = GzDecoder::new(data);
    let mut decompressed = Vec::new();
    decoder.read_to_end(&mut decompressed)?;
    Ok(decompressed)
}

fn parse_wav_sample_rate(data: &[u8]) -> Option<u32> {
    if data.len() < 28 || &data[0..4] != b"RIFF" || &data[8..12] != b"WAVE" {
        return None;
    }
    Some(u32::from_le_bytes([data[24], data[25], data[26], data[27]]))
}
