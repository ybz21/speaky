use crate::config::Config;
use log::{error, info};
use once_cell::sync::Lazy;
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use std::fs;
use std::time::{SystemTime, UNIX_EPOCH};

const MAX_HISTORY_SIZE: usize = 50;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryItem {
    pub text: String,
    pub timestamp: u64,
    pub engine: String,
    pub polished: bool,
}

static HISTORY: Lazy<Mutex<Vec<HistoryItem>>> = Lazy::new(|| Mutex::new(load()));

fn path() -> std::path::PathBuf {
    Config::config_dir().join("history.json")
}

fn load() -> Vec<HistoryItem> {
    let path = path();
    let Ok(content) = fs::read_to_string(path) else {
        return Vec::new();
    };
    serde_json::from_str(&content).unwrap_or_else(|error| {
        error!("Failed to load recognition history: {}", error);
        Vec::new()
    })
}

fn save(items: &[HistoryItem]) {
    let path = path();
    if let Some(parent) = path.parent() {
        if let Err(error) = fs::create_dir_all(parent) {
            error!("Failed to create history directory: {}", error);
            return;
        }
    }
    match serde_json::to_vec_pretty(items) {
        Ok(content) => {
            if let Err(error) = fs::write(&path, content) {
                error!("Failed to save recognition history: {}", error);
            }
        }
        Err(error) => error!("Failed to encode recognition history: {}", error),
    }
}

pub fn add(text: &str, engine: &str, polished: bool) {
    let text = text.trim();
    if text.is_empty() {
        return;
    }

    let mut items = HISTORY.lock();
    if let Some(index) = items.iter().take(5).position(|item| item.text == text) {
        items.remove(index);
    }
    items.insert(
        0,
        HistoryItem {
            text: text.to_string(),
            timestamp: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
            engine: engine.to_string(),
            polished,
        },
    );
    items.truncate(MAX_HISTORY_SIZE);
    save(&items);
    info!("Saved recognition result to history");
}

pub fn recent(count: usize) -> Vec<HistoryItem> {
    HISTORY.lock().iter().take(count).cloned().collect()
}

pub fn clear() {
    let mut items = HISTORY.lock();
    items.clear();
    save(&items);
    info!("Recognition history cleared");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn history_item_round_trip() {
        let item = HistoryItem {
            text: "hello".into(),
            timestamp: 1,
            engine: "test".into(),
            polished: false,
        };
        let encoded = serde_json::to_string(&item).unwrap();
        let decoded: HistoryItem = serde_json::from_str(&encoded).unwrap();
        assert_eq!(decoded.text, "hello");
    }
}
