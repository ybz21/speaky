mod openai;
mod volcengine;

pub use openai::OpenAIEngine;
pub use volcengine::VolcBigModelEngine;

use crate::config::Config;

/// Callback type for partial results
pub type PartialResultCallback = Box<dyn Fn(&str) + Send + Sync>;

/// Trait for ASR engines
pub trait Engine: Send + Sync {
    /// Get engine name
    fn name(&self) -> &str;

    /// Check if engine is available (has required credentials)
    fn is_available(&self) -> bool;

    /// Transcribe audio to text
    fn transcribe(&self, audio_data: &[u8], language: &str) -> Result<String, String>;

    /// Transcribe with partial results callback
    fn transcribe_with_callback(
        &self,
        audio_data: &[u8],
        language: &str,
        callback: PartialResultCallback,
    ) -> Result<String, String> {
        // Default implementation ignores callback
        let _ = callback;
        self.transcribe(audio_data, language)
    }

    /// Check if engine supports streaming
    fn supports_streaming(&self) -> bool {
        false
    }
}

/// Create engine based on configuration
pub fn create_engine(config: &Config) -> Option<Box<dyn Engine + Send + Sync>> {
    match config.engine.current.as_str() {
        "volc_bigmodel" => {
            let engine = VolcBigModelEngine::new(
                &config.engine.volc_bigmodel.app_key,
                &config.engine.volc_bigmodel.access_key,
            );
            if engine.is_available() {
                Some(Box::new(engine))
            } else {
                log::warn!("Volcengine BigModel engine not configured");
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
                Some(Box::new(engine))
            } else {
                log::warn!("OpenAI engine not configured");
                None
            }
        }
        _ => {
            log::error!("Unknown engine: {}", config.engine.current);
            None
        }
    }
}
