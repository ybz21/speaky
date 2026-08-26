use crate::{history, permissions, APP_STATE};
use log::{error, info};
use tauri::menu::{IsMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Wry};
use tauri_plugin_autostart::ManagerExt as AutostartExt;
use tauri_plugin_clipboard_manager::ClipboardExt;

const TRAY_ID: &str = "speaky-main";

fn is_english() -> bool {
    APP_STATE
        .config
        .read()
        .appearance
        .ui_language
        .to_lowercase()
        .starts_with("en")
}

fn label(zh: &str, en: &str) -> String {
    if is_english() {
        en.to_string()
    } else {
        zh.to_string()
    }
}

fn build_menu(app: &AppHandle) -> tauri::Result<Menu<Wry>> {
    let config = APP_STATE.config.read().clone();
    let settings = MenuItem::with_id(
        app,
        "settings",
        label("设置", "Settings"),
        true,
        None::<&str>,
    )?;
    let polish_label = if config.core.asr.llm_polish {
        label("✓ AI 润色", "✓ AI polish")
    } else {
        label("AI 润色", "AI polish")
    };
    let polish = MenuItem::with_id(app, "ai_polish", polish_label, true, None::<&str>)?;
    let autostart_label = if config.desktop.auto_start {
        label("✓ 开机自启动", "✓ Start at login")
    } else {
        label("开机自启动", "Start at login")
    };
    let autostart = MenuItem::with_id(app, "autostart", autostart_label, true, None::<&str>)?;

    let history = history::recent(10);
    let mut history_items = Vec::new();
    if history.is_empty() {
        history_items.push(MenuItem::with_id(
            app,
            "history_empty",
            label("暂无记录", "No history"),
            false,
            None::<&str>,
        )?);
    } else {
        for (index, item) in history.iter().enumerate() {
            let one_line = item.text.replace(['\n', '\r'], " ");
            let mut display: String = one_line.chars().take(40).collect();
            if one_line.chars().count() > 40 {
                display.push('…');
            }
            history_items.push(MenuItem::with_id(
                app,
                format!("history_{}", index),
                display,
                true,
                None::<&str>,
            )?);
        }
        history_items.push(MenuItem::with_id(
            app,
            "history_clear",
            label("清空历史", "Clear history"),
            true,
            None::<&str>,
        )?);
    }
    let history_refs: Vec<&dyn IsMenuItem<Wry>> = history_items
        .iter()
        .map(|item| item as &dyn IsMenuItem<Wry>)
        .collect();
    let history_menu = Submenu::with_items(
        app,
        label("最近识别", "Recent recognition"),
        true,
        &history_refs,
    )?;

    let diagnostics = MenuItem::with_id(
        app,
        "diagnostics",
        label("诊断", "Diagnostics"),
        true,
        None::<&str>,
    )?;
    let permission_status = permissions::status();
    let permissions_item = MenuItem::with_id(
        app,
        "permissions",
        label("权限设置", "Permission settings"),
        true,
        None::<&str>,
    )?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", label("退出", "Quit"), true, None::<&str>)?;

    let mut items: Vec<&dyn IsMenuItem<Wry>> =
        vec![&settings, &polish, &autostart, &history_menu, &diagnostics];
    if matches!(
        permission_status.microphone.as_str(),
        "denied" | "not_determined"
    ) || permission_status.accessibility == "denied"
    {
        items.push(&permissions_item);
    }
    items.push(&separator);
    items.push(&quit);
    Menu::with_items(app, &items)
}

pub fn install(app: &AppHandle) -> tauri::Result<()> {
    sync_autostart(app);
    let menu = build_menu(app)?;
    TrayIconBuilder::with_id(TRAY_ID)
        .icon(tauri::image::Image::from_bytes(include_bytes!(
            "../icons/32x32.png"
        ))?)
        .tooltip("Speaky")
        .menu(&menu)
        .on_menu_event(handle_menu_event)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                if let Err(error) = crate::show_settings_window(tray.app_handle()) {
                    error!("Failed to show settings window: {}", error);
                }
            }
        })
        .build(app)?;
    Ok(())
}

pub fn refresh(app: &AppHandle) {
    let Some(tray) = app.tray_by_id(TRAY_ID) else {
        return;
    };
    match build_menu(app) {
        Ok(menu) => {
            if let Err(error) = tray.set_menu(Some(menu)) {
                error!("Failed to refresh tray menu: {}", error);
            }
        }
        Err(error) => error!("Failed to rebuild tray menu: {}", error),
    }
}

fn handle_menu_event(app: &AppHandle, event: tauri::menu::MenuEvent) {
    let id = event.id().as_ref();
    match id {
        "settings" => {
            if let Err(error) = crate::show_settings_window(app) {
                error!("Failed to show settings: {}", error);
            }
        }
        "diagnostics" => {
            if let Err(error) = crate::show_diagnostics_window(app) {
                error!("Failed to show diagnostics: {}", error);
            }
        }
        "ai_polish" => {
            let mut config = APP_STATE.config.write();
            config.core.asr.llm_polish = !config.core.asr.llm_polish;
            if config.core.asr.llm_polish && !crate::polish::is_configured(&config) {
                info!("AI polish enabled but no LLM credential is configured; recognition will fall back safely");
            }
            if let Err(error) = config.save() {
                error!("Failed to save AI polish setting: {}", error);
            }
            drop(config);
            refresh(app);
        }
        "autostart" => {
            let enabled = !APP_STATE.config.read().desktop.auto_start;
            let result = if enabled {
                app.autolaunch().enable()
            } else {
                app.autolaunch().disable()
            };
            match result {
                Ok(()) => {
                    let mut config = APP_STATE.config.write();
                    config.desktop.auto_start = enabled;
                    let _ = config.save();
                    drop(config);
                    refresh(app);
                }
                Err(error) => error!("Failed to update autostart: {}", error),
            }
        }
        "history_clear" => {
            history::clear();
            refresh(app);
        }
        "permissions" => {
            if let Err(error) = permissions::open_settings() {
                error!("Failed to open permission settings: {}", error);
            }
        }
        "quit" => app.exit(0),
        _ if id.starts_with("history_") => {
            if let Ok(index) = id.trim_start_matches("history_").parse::<usize>() {
                if let Some(item) = history::recent(10).get(index) {
                    if let Err(error) = app.clipboard().write_text(item.text.clone()) {
                        error!("Failed to copy history item: {}", error);
                    }
                }
            }
        }
        _ => {}
    }
}

pub fn sync_autostart(app: &AppHandle) {
    migrate_legacy_autostart();
    let enabled = APP_STATE.config.read().desktop.auto_start;
    let result = if enabled {
        app.autolaunch().enable()
    } else {
        app.autolaunch().disable()
    };
    if let Err(error) = result {
        error!("Failed to synchronize autostart setting: {}", error);
    }
}

/// Remove the Python-era Linux desktop entry after the Tauri autostart entry
/// has taken ownership. Keeping both would launch two tray icons at login.
#[cfg(target_os = "linux")]
fn migrate_legacy_autostart() {
    let Some(config_dir) = dirs::config_dir() else {
        return;
    };
    let legacy = config_dir.join("autostart").join("speaky.desktop");
    let is_speaky_entry = std::fs::read_to_string(&legacy)
        .map(|content| content.contains("Name=Speaky"))
        .unwrap_or(false);
    if is_speaky_entry {
        match std::fs::remove_file(&legacy) {
            Ok(()) => info!("Removed legacy Python autostart entry"),
            Err(error) => error!("Failed to remove legacy autostart entry: {}", error),
        }
    }
}

#[cfg(not(target_os = "linux"))]
fn migrate_legacy_autostart() {}
