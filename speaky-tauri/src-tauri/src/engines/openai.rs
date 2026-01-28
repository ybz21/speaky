use super::Engine;
use log::{error, info};
use reqwest::blocking::multipart;

/// OpenAI Whisper API engine
pub struct OpenAIEngine {
    api_key: String,
    model: String,
    base_url: String,
}

impl OpenAIEngine {
    pub fn new(api_key: &str, model: &str, base_url: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            model: model.to_string(),
            base_url: base_url.trim_end_matches('/').to_string(),
        }
    }
}

impl Engine for OpenAIEngine {
    fn name(&self) -> &str {
        "OpenAI Whisper"
    }

    fn is_available(&self) -> bool {
        !self.api_key.is_empty()
    }

    fn transcribe(&self, audio_data: &[u8], language: &str) -> Result<String, String> {
        info!("Starting OpenAI transcription, model={}", self.model);

        let url = format!("{}/audio/transcriptions", self.base_url);

        // Create multipart form
        let part = multipart::Part::bytes(audio_data.to_vec())
            .file_name("audio.wav")
            .mime_str("audio/wav")
            .map_err(|e: reqwest::Error| e.to_string())?;

        let form = multipart::Form::new()
            .part("file", part)
            .text("model", self.model.clone())
            .text("language", language.to_string())
            .text("response_format", "text");

        let client = reqwest::blocking::Client::new();
        let response = client
            .post(&url)
            .bearer_auth(&self.api_key)
            .multipart(form)
            .send()
            .map_err(|e| format!("Request failed: {}", e))?;

        if !response.status().is_success() {
            let status = response.status();
            let text = response.text().unwrap_or_default();
            error!("OpenAI API error: {} - {}", status, text);
            return Err(format!("API error: {} - {}", status, text));
        }

        let text = response.text().map_err(|e| format!("Failed to read response: {}", e))?;
        info!("Transcription complete: {}", text.trim());
        Ok(text.trim().to_string())
    }

    fn supports_streaming(&self) -> bool {
        false
    }
}
