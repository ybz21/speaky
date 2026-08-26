use log::{info, warn};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use thiserror::Error;

/// Configuration-related errors
#[derive(Error, Debug)]
pub enum ConfigError {
    #[error("Config file not found at {path}")]
    NotFound { path: PathBuf },

    #[error("Failed to read config file: {source}")]
    ReadError { source: std::io::Error },

    #[error("Failed to parse config YAML: {source}")]
    ParseError { source: serde_yaml::Error },

    #[error("Failed to write config file: {source}")]
    WriteError { source: std::io::Error },

    #[error("Config directory creation failed: {source}")]
    DirCreationError { source: std::io::Error },

    #[error("Invalid config value: {message}")]
    ValidationError { message: String },
}

impl ConfigError {
    fn read_error(source: std::io::Error) -> Self {
        ConfigError::ReadError { source }
    }

    fn parse_error(source: serde_yaml::Error) -> Self {
        ConfigError::ParseError { source }
    }

    fn write_error(source: std::io::Error) -> Self {
        ConfigError::WriteError { source }
    }

    fn dir_creation_error(source: std::io::Error) -> Self {
        ConfigError::DirCreationError { source }
    }

    fn validation_error(message: String) -> Self {
        ConfigError::ValidationError { message }
    }
}

/// ASR configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AsrConfig {
    #[serde(default = "default_hotkey")]
    pub hotkey: String,
    #[serde(default = "default_hold_time")]
    pub hotkey_hold_time: f64,
    #[serde(default = "default_language")]
    pub language: String,
    #[serde(default = "default_streaming_mode")]
    pub streaming_mode: bool,
    #[serde(default)]
    pub audio_device: Option<u32>,
    /// Stable device label used to recover the selection when ALSA/PipeWire
    /// renumbers devices after a reconnect or audio-service restart.
    #[serde(default)]
    pub audio_device_name: Option<String>,
    #[serde(default = "default_audio_gain")]
    pub audio_gain: f64,
    #[serde(default = "default_sound_notification")]
    pub sound_notification: bool,
    #[serde(default)]
    pub llm_polish: bool,
}

fn default_hotkey() -> String {
    "ctrl".to_string()
}
fn default_hold_time() -> f64 {
    1.0
}
fn default_language() -> String {
    "auto".to_string()
}
fn default_streaming_mode() -> bool {
    true
}
fn default_audio_gain() -> f64 {
    1.0
}
fn default_sound_notification() -> bool {
    true
}

impl Default for AsrConfig {
    fn default() -> Self {
        Self {
            hotkey: default_hotkey(),
            hotkey_hold_time: default_hold_time(),
            language: default_language(),
            streaming_mode: default_streaming_mode(),
            audio_device: None,
            audio_device_name: None,
            audio_gain: default_audio_gain(),
            sound_notification: default_sound_notification(),
            llm_polish: false,
        }
    }
}

/// OpenAI-compatible text model used only for optional recognition polishing.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmOpenAIConfig {
    #[serde(default)]
    pub api_key: String,
    #[serde(default = "default_llm_model")]
    pub model: String,
    #[serde(default = "default_openai_base_url")]
    pub base_url: String,
}

fn default_llm_model() -> String {
    "gpt-4o-mini".to_string()
}

impl Default for LlmOpenAIConfig {
    fn default() -> Self {
        Self {
            api_key: String::new(),
            model: default_llm_model(),
            base_url: default_openai_base_url(),
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LlmConfig {
    #[serde(default)]
    pub openai: LlmOpenAIConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DesktopConfig {
    #[serde(default = "default_auto_start")]
    pub auto_start: bool,
}

fn default_auto_start() -> bool {
    true
}

impl Default for DesktopConfig {
    fn default() -> Self {
        Self {
            auto_start: default_auto_start(),
        }
    }
}

impl AsrConfig {
    /// Validate ASR configuration
    pub fn validate(&self) -> Result<(), ConfigError> {
        // Validate hotkey is not empty
        if self.hotkey.is_empty() {
            return Err(ConfigError::validation_error(
                "Hotkey cannot be empty".to_string(),
            ));
        }

        // Validate hold time is positive
        if self.hotkey_hold_time <= 0.0 {
            return Err(ConfigError::validation_error(format!(
                "Hold time must be positive, got {}",
                self.hotkey_hold_time
            )));
        }

        // Validate audio gain range
        if !(0.1..=10.0).contains(&self.audio_gain) {
            warn!(
                "Audio gain {} outside typical range [0.1, 10.0]",
                self.audio_gain
            );
        }

        Ok(())
    }
}

/// Core configuration
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CoreConfig {
    #[serde(default)]
    pub asr: AsrConfig,
}

/// Volcengine BigModel configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VolcBigModelConfig {
    /// New console authentication (X-Api-Key).
    #[serde(default)]
    pub api_key: String,
    #[serde(default)]
    pub app_key: String,
    #[serde(default)]
    pub access_key: String,
    #[serde(default = "default_volc_resource_id")]
    pub resource_id: String,
}

fn default_volc_resource_id() -> String {
    "volc.bigasr.sauc.duration".to_string()
}

impl Default for VolcBigModelConfig {
    fn default() -> Self {
        Self {
            api_key: String::new(),
            app_key: String::new(),
            access_key: String::new(),
            resource_id: default_volc_resource_id(),
        }
    }
}

/// OpenAI configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OpenAIConfig {
    #[serde(default)]
    pub api_key: String,
    #[serde(default = "default_openai_model")]
    pub model: String,
    #[serde(default = "default_openai_base_url")]
    pub base_url: String,
}

fn default_openai_model() -> String {
    "gpt-4o-transcribe".to_string()
}
fn default_openai_base_url() -> String {
    "https://api.openai.com/v1".to_string()
}

impl Default for OpenAIConfig {
    fn default() -> Self {
        Self {
            api_key: String::new(),
            model: default_openai_model(),
            base_url: default_openai_base_url(),
        }
    }
}

/// Engine configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineConfig {
    #[serde(default = "default_engine")]
    pub current: String,
    #[serde(default)]
    pub volc_bigmodel: VolcBigModelConfig,
    #[serde(default)]
    pub openai: OpenAIConfig,
}

fn default_engine() -> String {
    "volc_bigmodel".to_string()
}

impl Default for EngineConfig {
    fn default() -> Self {
        Self {
            current: default_engine(),
            volc_bigmodel: VolcBigModelConfig::default(),
            openai: OpenAIConfig::default(),
        }
    }
}

/// Appearance configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppearanceConfig {
    #[serde(default = "default_theme")]
    pub theme: String,
    #[serde(default = "default_ui_language")]
    pub ui_language: String,
    #[serde(default = "default_show_waveform")]
    pub show_waveform: bool,
    #[serde(default = "default_window_opacity")]
    pub window_opacity: f64,
}

fn default_theme() -> String {
    "auto".to_string()
}
fn default_ui_language() -> String {
    "zh-CN".to_string()
}
fn default_show_waveform() -> bool {
    true
}
fn default_window_opacity() -> f64 {
    0.9
}

impl Default for AppearanceConfig {
    fn default() -> Self {
        Self {
            theme: default_theme(),
            ui_language: default_ui_language(),
            show_waveform: default_show_waveform(),
            window_opacity: default_window_opacity(),
        }
    }
}

/// Main configuration struct
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Config {
    #[serde(default)]
    pub core: CoreConfig,
    #[serde(default)]
    pub engine: EngineConfig,
    #[serde(default)]
    pub appearance: AppearanceConfig,
    #[serde(default)]
    pub llm: LlmConfig,
    #[serde(default)]
    pub desktop: DesktopConfig,
}

impl Config {
    /// Validate entire configuration
    pub fn validate(&self) -> Result<(), ConfigError> {
        self.core.asr.validate()?;
        Ok(())
    }
    /// Get the config directory path
    pub fn config_dir() -> PathBuf {
        dirs::config_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("speaky")
    }

    /// Get the config file path
    pub fn config_path() -> PathBuf {
        Self::config_dir().join("config.yaml")
    }

    /// Load configuration from file
    pub fn load() -> Result<Self, ConfigError> {
        let path = Self::config_path();
        info!("Loading config from {:?}", path);

        if !path.exists() {
            info!("Config file not found, using defaults");
            return Ok(Self::default());
        }

        let content = fs::read_to_string(&path).map_err(|e| ConfigError::read_error(e))?;
        let config: Config =
            serde_yaml::from_str(&content).map_err(|e| ConfigError::parse_error(e))?;
        info!("Config loaded successfully");
        Ok(config)
    }

    /// Save configuration to file
    pub fn save(&self) -> Result<(), ConfigError> {
        let dir = Self::config_dir();
        if !dir.exists() {
            fs::create_dir_all(&dir).map_err(|e| ConfigError::dir_creation_error(e))?;
        }

        let path = Self::config_path();
        info!("Saving config to {:?}", path);

        let content = serde_yaml::to_string(self).map_err(|e| ConfigError::parse_error(e))?;
        fs::write(&path, content).map_err(|e| ConfigError::write_error(e))?;
        info!("Config saved successfully");
        Ok(())
    }
}
