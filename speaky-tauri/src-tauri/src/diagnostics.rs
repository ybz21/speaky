use crate::audio::AudioRecorder;
use crate::config::Config;
use crate::permissions::{self, PermissionStatus};
use crate::APP_STATE;
use serde::Serialize;
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const MAX_LOG_VIEW_BYTES: usize = 250_000;

#[derive(Debug, Clone, Serialize)]
pub struct DiagnosticDevice {
    pub index: u32,
    pub name: String,
    pub selected: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct DiagnosticSnapshot {
    pub app_version: String,
    pub platform: String,
    pub microphone_ready: bool,
    pub devices: Vec<DiagnosticDevice>,
    pub permissions: PermissionStatus,
    pub engine: String,
    pub engine_ready: bool,
    pub log_path: String,
}

pub fn log_path() -> PathBuf {
    Config::config_dir().join("speaky.log")
}

pub fn init_logging() -> Result<(), fern::InitError> {
    let path = log_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let file = fern::log_file(path)?;
    fern::Dispatch::new()
        .format(|out, message, record| {
            let timestamp = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs();
            out.finish(format_args!(
                "{} [{}] [{}] {}",
                timestamp,
                record.level(),
                record.target(),
                message
            ))
        })
        .level(log::LevelFilter::Info)
        .chain(std::io::stdout())
        .chain(file)
        .apply()?;
    Ok(())
}

pub fn snapshot() -> DiagnosticSnapshot {
    let config = APP_STATE.config.read().clone();
    let selected = config.core.asr.audio_device;
    let devices = AudioRecorder::get_devices()
        .into_iter()
        .map(|(index, name)| DiagnosticDevice {
            index,
            name,
            selected: selected == Some(index) || (selected.is_none() && index == 0),
        })
        .collect();
    DiagnosticSnapshot {
        app_version: env!("CARGO_PKG_VERSION").to_string(),
        platform: std::env::consts::OS.to_string(),
        microphone_ready: APP_STATE.recorder.read().is_some(),
        devices,
        permissions: permissions::status(),
        engine: config.engine.current,
        engine_ready: APP_STATE.engine.read().is_some(),
        log_path: log_path().display().to_string(),
    }
}

pub fn read_log() -> Result<String, String> {
    let bytes = match fs::read(log_path()) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(String::new()),
        Err(error) => return Err(error.to_string()),
    };
    let start = bytes.len().saturating_sub(MAX_LOG_VIEW_BYTES);
    Ok(String::from_utf8_lossy(&bytes[start..]).to_string())
}

pub fn clear_log() -> Result<(), String> {
    fs::OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(log_path())
        .map(|_| ())
        .map_err(|error| error.to_string())
}

pub fn export_log() -> Result<String, String> {
    let destination_dir = dirs::download_dir()
        .or_else(dirs::document_dir)
        .unwrap_or_else(Config::config_dir);
    fs::create_dir_all(&destination_dir).map_err(|error| error.to_string())?;
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let destination = destination_dir.join(format!("speaky-diagnostics-{}.log", timestamp));
    let snapshot = snapshot();
    let mut file = fs::File::create(&destination).map_err(|error| error.to_string())?;
    writeln!(file, "Speaky {} diagnostics", snapshot.app_version).map_err(|e| e.to_string())?;
    writeln!(file, "Platform: {}", snapshot.platform).map_err(|e| e.to_string())?;
    writeln!(file, "Microphone ready: {}", snapshot.microphone_ready).map_err(|e| e.to_string())?;
    writeln!(file, "Permissions: {:?}", snapshot.permissions).map_err(|e| e.to_string())?;
    writeln!(
        file,
        "Engine: {} ({})",
        snapshot.engine, snapshot.engine_ready
    )
    .map_err(|e| e.to_string())?;
    writeln!(file, "\n--- Log ---\n{}", read_log()?).map_err(|e| e.to_string())?;
    Ok(destination.display().to_string())
}
