mod openai;
mod volcengine;

pub use openai::OpenAIEngine;
pub use volcengine::{VolcBigModelEngine, VolcRealtimeSession};

use crate::config::Config;
use log::{info, warn};

/// Callback type for partial transcription results
///
/// This callback is invoked during streaming transcription to provide
/// incremental results as they become available.
pub type PartialResultCallback = Box<dyn Fn(&str) + Send + Sync>;

/// Result type for engine operations
pub type EngineResult = Result<String, EngineError>;

/// Errors that can occur during engine operations
#[derive(Debug, Clone, PartialEq)]
pub enum EngineError {
    /// Engine not properly configured (missing API keys, etc.)
    NotConfigured,

    /// Network or API error
    NetworkError(String),

    /// Audio processing error
    AudioProcessingError(String),

    /// Invalid response from API
    InvalidResponse(String),

    /// Rate limiting or quota exceeded
    RateLimited(String),

    /// Unknown error
    Unknown(String),
}

impl std::fmt::Display for EngineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EngineError::NotConfigured => write!(f, "Engine not configured"),
            EngineError::NetworkError(msg) => write!(f, "Network error: {}", msg),
            EngineError::AudioProcessingError(msg) => write!(f, "Audio processing error: {}", msg),
            EngineError::InvalidResponse(msg) => write!(f, "Invalid response: {}", msg),
            EngineError::RateLimited(msg) => write!(f, "Rate limited: {}", msg),
            EngineError::Unknown(msg) => write!(f, "Unknown error: {}", msg),
        }
    }
}

impl std::error::Error for EngineError {}

/// Trait for ASR (Automatic Speech Recognition) engines
///
/// Implement this trait to add support for different speech recognition
/// backends. Each engine handles the communication with its respective
/// API and audio transcription.
pub trait Engine: Send + Sync {
    /// Get the human-readable name of this engine
    ///
    /// # Returns
    /// A string identifier for the engine (e.g., "OpenAI", "Volcengine BigModel")
    fn name(&self) -> &str;

    /// Check if engine is properly configured and ready to use
    ///
    /// # Returns
    /// true if required credentials are present, false otherwise
    fn is_available(&self) -> bool;

    /// Transcribe audio data to text
    ///
    /// # Arguments
    /// * `audio_data` - WAV-encoded audio bytes
    /// * `language` - ISO language code (e.g., "zh", "en")
    ///
    /// # Returns
    /// Transcription result or error
    fn transcribe(&self, audio_data: &[u8], language: &str) -> EngineResult;

    /// Transcribe with partial results callback
    ///
    /// This method supports streaming transcription where partial
    /// results are provided via the callback as transcription progresses.
    ///
    /// # Arguments
    /// * `audio_data` - WAV-encoded audio bytes
    /// * `language` - ISO language code
    /// * `callback` - Function to receive partial results
    ///
    /// # Returns
    /// Final transcription result or error
    fn transcribe_with_callback(
        &self,
        audio_data: &[u8],
        language: &str,
        callback: PartialResultCallback,
    ) -> EngineResult {
        // Default implementation ignores callback for non-streaming engines
        let _ = callback;
        self.transcribe(audio_data, language)
    }

    /// Check if engine supports streaming transcription
    ///
    /// # Returns
    /// true if streaming is supported, false otherwise
    fn supports_streaming(&self) -> bool {
        false
    }
}

/// Create an engine based on configuration
///
/// This function instantiates the appropriate engine based on the
/// current configuration settings. If the configured engine is not
/// available (missing credentials), a warning is logged and None
/// is returned.
///
/// # Arguments
/// * `config` - Application configuration
///
/// # Returns
/// Some(Box<dyn Engine>) if engine is available, None otherwise
pub fn create_engine(config: &Config) -> Option<Box<dyn Engine + Send + Sync>> {
    match config.engine.current.as_str() {
        "volc_bigmodel" => {
            // Allow ephemeral local testing without persisting credentials in
            // config.yaml. The settings value takes precedence.
            let api_key = if config.engine.volc_bigmodel.api_key.is_empty() {
                std::env::var("SPEAKY_VOLC_API_KEY").unwrap_or_default()
            } else {
                config.engine.volc_bigmodel.api_key.clone()
            };
            let engine = VolcBigModelEngine::new(
                &api_key,
                &config.engine.volc_bigmodel.app_key,
                &config.engine.volc_bigmodel.access_key,
                &config.engine.volc_bigmodel.resource_id,
            );
            if engine.is_available() {
                info!("Using Volcengine BigModel engine");
                Some(Box::new(engine))
            } else {
                warn!("Volcengine BigModel engine not configured (missing credentials)");
                None
            }
        }
        "openai" => {
            let engine = OpenAIEngine::new(
                &config.engine.openai.api_key,
                &config.engine.openai.model,
                &config.engine.openai.base_url,
            );
            if engine.is_available() {
                info!(
                    "Using OpenAI engine (model: {})",
                    config.engine.openai.model
                );
                Some(Box::new(engine))
            } else {
                warn!("OpenAI engine not configured (missing API key)");
                None
            }
        }
        _ => {
            warn!(
                "Unknown engine: {}, falling back to none",
                config.engine.current
            );
            None
        }
    }
}
