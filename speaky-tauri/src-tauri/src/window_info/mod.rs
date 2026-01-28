//! Window information utilities for getting focused app name and icon.

use log::{debug, warn};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Mutex;
use once_cell::sync::Lazy;

/// Information about the focused window
#[derive(Debug, Clone, Default)]
pub struct WindowInfo {
    pub wm_class: String,
    pub wm_instance: String,
    pub window_name: String,
    pub app_name: String,
    pub icon_path: Option<String>,
}

/// Cache for desktop entries
static DESKTOP_CACHE: Lazy<Mutex<HashMap<String, DesktopEntry>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

/// Cache for icon paths
static ICON_CACHE: Lazy<Mutex<HashMap<String, Option<String>>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

#[derive(Debug, Clone)]
struct DesktopEntry {
    name: String,
    icon: Option<String>,
    startup_wm_class: Option<String>,
}

/// Get information about the currently focused window
pub fn get_focused_window_info() -> Option<WindowInfo> {
    #[cfg(target_os = "linux")]
    {
        get_linux_window_info()
    }
    #[cfg(not(target_os = "linux"))]
    {
        None
    }
}

#[cfg(target_os = "linux")]
fn get_linux_window_info() -> Option<WindowInfo> {
    // Get active window ID
    let output = Command::new("xprop")
        .args(["-root", "_NET_ACTIVE_WINDOW"])
        .output()
        .ok()?;

    if !output.status.success() {
        return None;
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let window_id = extract_hex_id(&stdout)?;

    // Get WM_CLASS
    let output = Command::new("xprop")
        .args(["-id", &window_id, "WM_CLASS"])
        .output()
        .ok()?;

    let (wm_class, wm_instance) = if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        parse_wm_class(&stdout)
    } else {
        (String::new(), String::new())
    };

    // Get window name
    let output = Command::new("xprop")
        .args(["-id", &window_id, "_NET_WM_NAME"])
        .output()
        .ok()?;

    let window_name = if output.status.success() {
        let stdout = String::from_utf8_lossy(&output.stdout);
        extract_quoted_string(&stdout).unwrap_or_default()
    } else {
        String::new()
    };

    // Find app name and icon
    let app_name = if !wm_class.is_empty() {
        wm_class.clone()
    } else if !wm_instance.is_empty() {
        wm_instance.clone()
    } else {
        "Unknown".to_string()
    };

    // Try to get better app name from desktop entry
    let desktop_info = find_desktop_entry(&wm_class, &wm_instance);
    let final_app_name = desktop_info
        .as_ref()
        .map(|e| e.name.clone())
        .unwrap_or(app_name);

    // Find icon
    let icon_path = find_icon_for_wm_class(&wm_class, &wm_instance);

    Some(WindowInfo {
        wm_class,
        wm_instance,
        window_name,
        app_name: final_app_name,
        icon_path,
    })
}

fn extract_hex_id(text: &str) -> Option<String> {
    let re = regex::Regex::new(r"0x[0-9a-fA-F]+").ok()?;
    re.find(text).map(|m| m.as_str().to_string())
}

fn parse_wm_class(text: &str) -> (String, String) {
    // WM_CLASS(STRING) = "cursor", "Cursor"
    let re = regex::Regex::new(r#""([^"]*)",\s*"([^"]*)""#).ok();
    if let Some(re) = re {
        if let Some(caps) = re.captures(text) {
            let instance = caps.get(1).map(|m| m.as_str().to_string()).unwrap_or_default();
            let class = caps.get(2).map(|m| m.as_str().to_string()).unwrap_or_default();
            return (class, instance);
        }
    }
    (String::new(), String::new())
}

fn extract_quoted_string(text: &str) -> Option<String> {
    let re = regex::Regex::new(r#""([^"]*)""#).ok()?;
    re.captures(text)
        .and_then(|caps| caps.get(1))
        .map(|m| m.as_str().to_string())
}

fn find_desktop_entry(wm_class: &str, wm_instance: &str) -> Option<DesktopEntry> {
    // Build cache if empty
    {
        let cache = DESKTOP_CACHE.lock().ok()?;
        if cache.is_empty() {
            drop(cache);
            build_desktop_cache();
        }
    }

    let cache = DESKTOP_CACHE.lock().ok()?;

    // Search by StartupWMClass first
    for entry in cache.values() {
        if let Some(ref startup_wm_class) = entry.startup_wm_class {
            let swc = startup_wm_class.to_lowercase();
            if swc == wm_class.to_lowercase() || swc == wm_instance.to_lowercase() {
                return Some(entry.clone());
            }
        }
    }

    // Search by filename match
    let search_terms = [wm_class.to_lowercase(), wm_instance.to_lowercase()];
    for term in &search_terms {
        if let Some(entry) = cache.get(term) {
            return Some(entry.clone());
        }
    }

    None
}

fn build_desktop_cache() {
    let desktop_dirs = [
        dirs::home_dir()
            .map(|h| h.join(".local/share/flatpak/exports/share/applications"))
            .unwrap_or_default(),
        dirs::home_dir()
            .map(|h| h.join(".local/share/applications"))
            .unwrap_or_default(),
        PathBuf::from("/var/lib/flatpak/exports/share/applications"),
        PathBuf::from("/usr/local/share/applications"),
        PathBuf::from("/usr/share/applications"),
    ];

    let mut cache = DESKTOP_CACHE.lock().unwrap();

    for dir_path in &desktop_dirs {
        if !dir_path.is_dir() {
            continue;
        }

        if let Ok(entries) = fs::read_dir(dir_path) {
            for entry in entries.filter_map(|e| e.ok()) {
                let path = entry.path();
                if path.extension().map(|e| e == "desktop").unwrap_or(false) {
                    if let Some(desktop_entry) = parse_desktop_file(&path) {
                        let key = path
                            .file_stem()
                            .and_then(|s| s.to_str())
                            .unwrap_or("")
                            .to_lowercase();
                        cache.insert(key, desktop_entry);
                    }
                }
            }
        }
    }
}

fn parse_desktop_file(filepath: &Path) -> Option<DesktopEntry> {
    let content = fs::read_to_string(filepath).ok()?;

    let mut name = None;
    let mut icon = None;
    let mut startup_wm_class = None;
    let mut in_desktop_entry = false;

    for line in content.lines() {
        let line = line.trim();
        if line == "[Desktop Entry]" {
            in_desktop_entry = true;
            continue;
        } else if line.starts_with('[') && line.ends_with(']') {
            in_desktop_entry = false;
            continue;
        }

        if !in_desktop_entry {
            continue;
        }

        if let Some((key, value)) = line.split_once('=') {
            let key = key.trim().to_lowercase();
            let value = value.trim();

            match key.as_str() {
                "name" if name.is_none() => name = Some(value.to_string()),
                "icon" => icon = Some(value.to_string()),
                "startupwmclass" => startup_wm_class = Some(value.to_string()),
                _ => {}
            }
        }
    }

    name.map(|n| DesktopEntry {
        name: n,
        icon,
        startup_wm_class,
    })
}

fn find_icon_for_wm_class(wm_class: &str, wm_instance: &str) -> Option<String> {
    let cache_key = format!("{}|{}", wm_class, wm_instance);

    // Check cache
    {
        let cache = ICON_CACHE.lock().ok()?;
        if let Some(icon) = cache.get(&cache_key) {
            return icon.clone();
        }
    }

    // Find desktop entry for icon name
    let entry = find_desktop_entry(wm_class, wm_instance);
    let icon_name = entry
        .as_ref()
        .and_then(|e| e.icon.clone())
        .unwrap_or_else(|| {
            if !wm_class.is_empty() {
                wm_class.to_lowercase()
            } else {
                wm_instance.to_lowercase()
            }
        });

    // Resolve icon path
    let icon_path = resolve_icon_path(&icon_name);

    // Cache result
    {
        if let Ok(mut cache) = ICON_CACHE.lock() {
            cache.insert(cache_key, icon_path.clone());
        }
    }

    icon_path
}

fn resolve_icon_path(icon_name: &str) -> Option<String> {
    if icon_name.is_empty() {
        return None;
    }

    // If it's already an absolute path
    if icon_name.starts_with('/') {
        if Path::new(icon_name).is_file() {
            return Some(icon_name.to_string());
        }
        // Extract basename and search
        let basename = Path::new(icon_name)
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or(icon_name);
        return resolve_icon_path(basename);
    }

    let home = dirs::home_dir().unwrap_or_default();

    // Icon directories (prefer larger sizes)
    let icon_dirs = [
        PathBuf::from("/usr/share/pixmaps"),
        PathBuf::from("/usr/share/icons/hicolor/256x256/apps"),
        PathBuf::from("/usr/share/icons/hicolor/128x128/apps"),
        PathBuf::from("/usr/share/icons/hicolor/96x96/apps"),
        PathBuf::from("/usr/share/icons/hicolor/64x64/apps"),
        PathBuf::from("/usr/share/icons/hicolor/48x48/apps"),
        PathBuf::from("/usr/share/icons/hicolor/scalable/apps"),
        home.join(".local/share/icons/hicolor/256x256/apps"),
        home.join(".local/share/icons/hicolor/128x128/apps"),
        home.join(".local/share/icons/hicolor/48x48/apps"),
        PathBuf::from("/var/lib/flatpak/exports/share/icons/hicolor/256x256/apps"),
        PathBuf::from("/var/lib/flatpak/exports/share/icons/hicolor/128x128/apps"),
    ];

    let extensions = [".png", ".svg", ".xpm", ""];

    for icon_dir in &icon_dirs {
        if !icon_dir.is_dir() {
            continue;
        }

        for ext in &extensions {
            let icon_path = icon_dir.join(format!("{}{}", icon_name, ext));
            if icon_path.is_file() {
                return icon_path.to_str().map(|s| s.to_string());
            }
        }
    }

    None
}
