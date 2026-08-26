use super::{Engine, EngineError, EngineResult};
use log::{debug, error};
use once_cell::sync::Lazy;
use reqwest::multipart;
use tokio::runtime::Runtime;

/// Recognition is called from a worker thread, so provide a runtime for the
/// async HTTP implementation instead of assuming a Tokio context exists.
static RUNTIME: Lazy<Runtime> = Lazy::new(|| {
    tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .thread_name("speaky-http")
        .worker_threads(2)
        .build()
        .expect("Failed to create Tokio runtime")
});

/// OpenAI Whisper API engine
///
/// This engine uses OpenAI's Whisper API for speech recognition.
/// It requires an API key to be configured in the application settings.
#[derive(Debug, Clone)]
pub struct OpenAIEngine {
    api_key: String,
    model: String,
    base_url: String,
    client: reqwest::Client,
}

impl OpenAIEngine {
    /// Create a new OpenAI engine instance
    ///
    /// # Arguments
    /// * `api_key` - OpenAI API key
    /// * `model` - Model name (e.g., "whisper-1", "gpt-4o-transcribe")
    /// * `base_url` - Base URL for API requests
    pub fn new(api_key: &str, model: &str, base_url: &str) -> Self {
        // Reusable HTTP client with timeout
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(60))
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());

        Self {
            api_key: api_key.to_string(),
            model: model.to_string(),
            base_url: base_url.trim_end_matches('/').to_string(),
            client,
        }
    }

    /// Async transcription implementation
    async fn transcribe_async(&self, audio_data: &[u8], language: &str) -> EngineResult {
        if audio_data.is_empty() {
            return Err(EngineError::AudioProcessingError(
                "Empty audio data provided".to_string(),
            ));
        }

        debug!(
            "Starting OpenAI transcription, model={}, language={}, size={} bytes",
            self.model,
            language,
            audio_data.len()
        );

        let url = format!("{}/audio/transcriptions", self.base_url);

        // Create multipart form with audio file
        let part = multipart::Part::bytes(audio_data.to_vec())
            .file_name("audio.wav")
            .mime_str("audio/wav")
            .map_err(|e: reqwest::Error| {
                EngineError::AudioProcessingError(format!("Failed to create multipart form: {}", e))
            })?;

        let mut form = multipart::Form::new()
            .part("file", part)
            .text("model", self.model.clone())
            .text("response_format", "text");

        // Omit the language field for automatic detection. BCP 47 values from
        // older configs are converted at this provider boundary when present.
        if !language.is_empty() && language != "auto" {
            form = form.text(
                "language",
                language
                    .split(['-', '_'])
                    .next()
                    .unwrap_or("zh")
                    .to_string(),
            );
        }

        let response = self
            .client
            .post(&url)
            .bearer_auth(&self.api_key)
            .multipart(form)
            .send()
            .await
            .map_err(|e| EngineError::NetworkError(format!("Request failed: {}", e)))?;

        if !response.status().is_success() {
            let status = response.status();
            let text = response.text().await.unwrap_or_default();
            error!("OpenAI API error: {} - {}", status, text);

            return Err(if status == 429 {
                EngineError::RateLimited("Rate limit exceeded".to_string())
            } else {
                EngineError::NetworkError(format!("API error {}: {}", status, text))
            });
        }

        let text = response
            .text()
            .await
            .map_err(|e| EngineError::InvalidResponse(format!("Failed to read response: {}", e)))?;

        let result = text.trim().to_string();
        debug!("Transcription complete: {} chars", result.len());
        Ok(result)
    }
}

impl Engine for OpenAIEngine {
    fn name(&self) -> &str {
        "OpenAI Whisper"
    }

    fn is_available(&self) -> bool {
        !self.api_key.is_empty()
    }

    fn transcribe(&self, audio_data: &[u8], language: &str) -> EngineResult {
        RUNTIME.block_on(self.transcribe_async(audio_data, language))
    }

    fn supports_streaming(&self) -> bool {
        false
    }
}
