use super::Engine;
use byteorder::{BigEndian, WriteBytesExt};
use flate2::write::GzEncoder;
use flate2::Compression;
use futures_util::{SinkExt, StreamExt};
use log::{debug, error, info};
use std::io::Write;
use tokio::runtime::Runtime;
use tokio_tungstenite::{
    connect_async,
    tungstenite::{http::Request, Message},
};
use uuid::Uuid;

// Protocol constants
const PROTOCOL_VERSION: u8 = 0b0001;
const MESSAGE_TYPE_FULL_REQUEST: u8 = 0b0001;
const MESSAGE_TYPE_AUDIO_ONLY: u8 = 0b0010;
const MESSAGE_TYPE_FULL_RESPONSE: u8 = 0b1001;
const MESSAGE_TYPE_ERROR_RESPONSE: u8 = 0b1111;
const FLAGS_POS_SEQUENCE: u8 = 0b0001;
const FLAGS_NEG_SEQUENCE: u8 = 0b0010;
const FLAGS_NEG_WITH_SEQUENCE: u8 = 0b0011;
const SERIALIZATION_JSON: u8 = 0b0001;
const COMPRESSION_GZIP: u8 = 0b0001;

/// Volcengine BigModel ASR engine
pub struct VolcBigModelEngine {
    app_key: String,
    access_key: String,
    ws_url: String,
    segment_duration_ms: u32,
}

impl VolcBigModelEngine {
    pub fn new(app_key: &str, access_key: &str) -> Self {
        Self {
            app_key: app_key.to_string(),
            access_key: access_key.to_string(),
            ws_url: "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async".to_string(),
            segment_duration_ms: 200,
        }
    }

    fn build_header(
        message_type: u8,
        flags: u8,
        serialization: u8,
        compression: u8,
    ) -> Vec<u8> {
        vec![
            (PROTOCOL_VERSION << 4) | 1, // version + header size
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0x00, // reserved
        ]
    }

    fn build_full_request(&self, seq: i32, sample_rate: u32) -> Vec<u8> {
        let header = Self::build_header(
            MESSAGE_TYPE_FULL_REQUEST,
            FLAGS_POS_SEQUENCE,
            SERIALIZATION_JSON,
            COMPRESSION_GZIP,
        );

        let payload = serde_json::json!({
            "user": {"uid": "speaky"},
            "audio": {
                "format": "wav",
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
            },
        });

        let payload_json = payload.to_string();
        let payload_compressed = gzip_compress(payload_json.as_bytes());

        let mut request = header;
        request.write_i32::<BigEndian>(seq).unwrap();
        request.write_u32::<BigEndian>(payload_compressed.len() as u32).unwrap();
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
        request.write_u32::<BigEndian>(compressed.len() as u32).unwrap();
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
            let _payload_size = u32::from_be_bytes([payload[0], payload[1], payload[2], payload[3]]);
            payload = &payload[4..];
        } else if message_type == MESSAGE_TYPE_ERROR_RESPONSE && payload.len() >= 8 {
            result.code = i32::from_be_bytes([payload[0], payload[1], payload[2], payload[3]]);
            let _payload_size = u32::from_be_bytes([payload[4], payload[5], payload[6], payload[7]]);
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
    ) -> Result<String, String> {
        let request_id = Uuid::new_v4().to_string();
        info!("Starting BigModel transcription, request_id={}", request_id);

        // Parse WAV to get sample rate
        let sample_rate = parse_wav_sample_rate(audio_data).unwrap_or(16000);
        info!("Audio sample rate: {}", sample_rate);

        // Build WebSocket request with custom headers
        let request = Request::builder()
            .uri(&self.ws_url)
            .header("X-Api-Resource-Id", "volc.seedasr.sauc.duration")
            .header("X-Api-Request-Id", &request_id)
            .header("X-Api-Access-Key", &self.access_key)
            .header("X-Api-App-Key", &self.app_key)
            .header("Host", "openspeech.bytedance.com")
            .header("Upgrade", "websocket")
            .header("Connection", "Upgrade")
            .header(
                "Sec-WebSocket-Key",
                tokio_tungstenite::tungstenite::handshake::client::generate_key(),
            )
            .header("Sec-WebSocket-Version", "13")
            .body(())
            .map_err(|e: tokio_tungstenite::tungstenite::http::Error| e.to_string())?;

        let (mut ws, _) = connect_async(request)
            .await
            .map_err(|e| format!("Failed to connect: {}", e))?;

        info!("Connected to WebSocket");

        // Send full request
        let full_request = self.build_full_request(1, sample_rate);
        ws.send(Message::Binary(full_request.into()))
            .await
            .map_err(|e| format!("Failed to send full request: {}", e))?;

        // Wait for initial response
        if let Some(msg) = ws.next().await {
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

            debug!("Sent segment {}/{}, last={}", i + 1, total_segments, is_last);

            if !is_last {
                seq += 1;
                tokio::time::sleep(tokio::time::Duration::from_millis(
                    self.segment_duration_ms as u64,
                ))
                .await;
            }
        }

        // Receive responses
        let mut result_text = String::new();

        while let Some(msg) = ws.next().await {
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
}

impl Engine for VolcBigModelEngine {
    fn name(&self) -> &str {
        "Volcengine BigModel"
    }

    fn is_available(&self) -> bool {
        !self.app_key.is_empty() && !self.access_key.is_empty()
    }

    fn transcribe(&self, audio_data: &[u8], language: &str) -> Result<String, String> {
        let rt = Runtime::new().map_err(|e| e.to_string())?;
        rt.block_on(self.transcribe_async(audio_data, language, None))
    }

    fn transcribe_with_callback(
        &self,
        audio_data: &[u8],
        language: &str,
        callback: super::PartialResultCallback,
    ) -> Result<String, String> {
        let rt = Runtime::new().map_err(|e| e.to_string())?;
        rt.block_on(self.transcribe_async(audio_data, language, Some(callback)))
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
