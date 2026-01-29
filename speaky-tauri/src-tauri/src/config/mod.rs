use log::info;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

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
    #[serde(default = "default_audio_gain")]
    pub audio_gain: f64,
    #[serde(default = "default_sound_notification")]
    pub sound_notification: bool,
}

fn default_hotkey() -> String {
    "ctrl".to_string()
}
fn default_hold_time() -> f64 {
    1.0
}
fn default_language() -> String {
    "zh".to_string()
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
            audio_gain: default_audio_gain(),
            sound_notification: default_sound_notification(),
        }
    }
}

/// Core configuration
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CoreConfig {
    #[serde(default)]
    pub asr: AsrConfig,
}

/// Volcengine BigModel configuration
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct VolcBigModelConfig {
    #[serde(default)]
    pub app_key: String,
    #[serde(default)]
    pub access_key: String,
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
    "auto".to_string()
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
}

impl Config {
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
    pub fn load() -> Result<Self, Box<dyn std::error::Error>> {
        let path = Self::config_path();
        info!("Loading config from {:?}", path);

        if !path.exists() {
            info!("Config file not found, using defaults");
            return Ok(Self::default());
        }

        let content = fs::read_to_string(&path)?;
        let config: Config = serde_yaml::from_str(&content)?;
        info!("Config loaded successfully");
        Ok(config)
    }

    /// Save configuration to file
    pub fn save(&self) -> Result<(), Box<dyn std::error::Error>> {
        let dir = Self::config_dir();
        if !dir.exists() {
            fs::create_dir_all(&dir)?;
        }

        let path = Self::config_path();
        info!("Saving config to {:?}", path);

        let content = serde_yaml::to_string(self)?;
        fs::write(&path, content)?;
        info!("Config saved successfully");
        Ok(())
    }
}
