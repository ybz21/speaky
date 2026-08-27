#[cfg(target_os = "linux")]
use std::fs;
#[cfg(target_os = "linux")]
use std::path::Path;
#[cfg(target_os = "linux")]
use std::process::Command;

#[cfg(target_os = "linux")]
const APP_ID: &str = "com.ybz21.speaky";
#[cfg(target_os = "linux")]
const LEGACY_APP_ID: &str = "com.speaky.app";

#[cfg(target_os = "linux")]
const ICON_PNG: &[u8] = include_bytes!("../icons/128x128@2x.png");
#[cfg(target_os = "linux")]
const ICON_SVG: &[u8] = include_bytes!("../../../resources/icon.svg");

/// Register the unpackaged development/release binary with the Linux desktop.
/// Packaged builds already install an entry, but a user-level entry keeps the
/// app icon and WM_CLASS association correct when running directly from target/.
#[cfg(target_os = "linux")]
pub fn install() -> Result<(), String> {
    let data_dir = dirs::data_local_dir().ok_or("Local data directory is unavailable")?;
    let executable = std::env::current_exe().map_err(|error| error.to_string())?;

    // The Debian package already owns the system desktop entry and icons.
    // Keeping a second user entry makes GNOME show two indistinguishable
    // Speaky applications. Clean up development-era entries when running the
    // installed binary and let dpkg remain the single source of truth.
    if is_deb_install(&executable) {
        remove_user_artifacts(&data_dir);
        refresh_desktop_database(&data_dir.join("applications"));
        return Ok(());
    }

    let applications_dir = data_dir.join("applications");
    let icon_dir = data_dir.join("icons");
    let hicolor_dir = icon_dir.join("hicolor/256x256/apps");
    let scalable_dir = icon_dir.join("hicolor/scalable/apps");
    for directory in [&applications_dir, &icon_dir, &hicolor_dir, &scalable_dir] {
        fs::create_dir_all(directory).map_err(|error| error.to_string())?;
    }
    remove_legacy_artifacts(&data_dir);

    let direct_icon = icon_dir.join(format!("{APP_ID}.png"));
    fs::write(&direct_icon, ICON_PNG).map_err(|error| error.to_string())?;
    fs::write(hicolor_dir.join(format!("{APP_ID}.png")), ICON_PNG)
        .map_err(|error| error.to_string())?;
    fs::write(scalable_dir.join(format!("{APP_ID}.svg")), ICON_SVG)
        .map_err(|error| error.to_string())?;

    let desktop_file = applications_dir.join(format!("{APP_ID}.desktop"));
    fs::write(&desktop_file, desktop_entry(&executable, &direct_icon))
        .map_err(|error| error.to_string())?;
    patch_autostart_entry(&direct_icon)?;

    // GNOME normally notices this directory itself. Refreshing the database
    // makes the association deterministic on desktops that cache it longer.
    refresh_desktop_database(&applications_dir);
    Ok(())
}

#[cfg(target_os = "linux")]
fn is_deb_install(executable: &Path) -> bool {
    executable == Path::new("/usr/bin/speaky")
}

#[cfg(target_os = "linux")]
fn remove_user_artifacts(data_dir: &Path) {
    remove_artifacts(data_dir, APP_ID);
    remove_artifacts(data_dir, LEGACY_APP_ID);
}

#[cfg(target_os = "linux")]
fn remove_legacy_artifacts(data_dir: &Path) {
    remove_artifacts(data_dir, LEGACY_APP_ID);
}

#[cfg(target_os = "linux")]
fn remove_artifacts(data_dir: &Path, app_id: &str) {
    let files = [
        data_dir.join(format!("applications/{app_id}.desktop")),
        data_dir.join(format!("icons/{app_id}.png")),
        data_dir.join(format!("icons/hicolor/256x256/apps/{app_id}.png")),
        data_dir.join(format!("icons/hicolor/scalable/apps/{app_id}.svg")),
    ];
    for file in files {
        if let Err(error) = fs::remove_file(&file) {
            if error.kind() != std::io::ErrorKind::NotFound {
                log::warn!(
                    "Failed to remove legacy desktop artifact {:?}: {}",
                    file,
                    error
                );
            }
        }
    }
}

#[cfg(target_os = "linux")]
fn refresh_desktop_database(applications_dir: &Path) {
    if applications_dir.is_dir() {
        let _ = Command::new("update-desktop-database")
            .arg(applications_dir)
            .output();
    }
}

#[cfg(not(target_os = "linux"))]
pub fn install() -> Result<(), String> {
    Ok(())
}

#[cfg(target_os = "linux")]
fn desktop_entry(executable: &Path, icon: &Path) -> String {
    format!(
        "[Desktop Entry]\nType=Application\nVersion=1.0\nName=Speaky\nComment=Cross-platform voice input\nExec={}\nIcon={}\nTerminal=false\nCategories=Utility;AudioVideo;\nStartupNotify=true\nStartupWMClass=Speaky\n",
        quote_exec_path(executable),
        icon.display()
    )
}

#[cfg(target_os = "linux")]
fn quote_exec_path(path: &Path) -> String {
    let escaped = path
        .to_string_lossy()
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('`', "\\`")
        .replace('$', "\\$");
    format!("\"{escaped}\"")
}

#[cfg(target_os = "linux")]
fn patch_autostart_entry(icon: &Path) -> Result<(), String> {
    let Some(config_dir) = dirs::config_dir() else {
        return Ok(());
    };
    let path = config_dir.join("autostart/Speaky.desktop");
    if !path.is_file() {
        return Ok(());
    }
    let content = fs::read_to_string(&path).map_err(|error| error.to_string())?;
    let content = upsert_field(&content, "Icon", &icon.display().to_string());
    let content = upsert_field(&content, "StartupWMClass", "Speaky");
    fs::write(path, content).map_err(|error| error.to_string())
}

#[cfg(target_os = "linux")]
fn upsert_field(content: &str, key: &str, value: &str) -> String {
    let prefix = format!("{key}=");
    let mut found = false;
    let mut lines = content
        .lines()
        .map(|line| {
            if line.starts_with(&prefix) {
                found = true;
                format!("{prefix}{value}")
            } else {
                line.to_string()
            }
        })
        .collect::<Vec<_>>();
    if !found {
        lines.push(format!("{prefix}{value}"));
    }
    format!("{}\n", lines.join("\n"))
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;

    #[test]
    fn desktop_entry_matches_tauri_window_class() {
        let entry = desktop_entry(
            Path::new("/tmp/Speaky App/speaky"),
            Path::new("/tmp/icon.png"),
        );
        assert!(entry.contains("Name=Speaky"));
        assert!(entry.contains("StartupWMClass=Speaky"));
        assert!(entry.contains("Icon=/tmp/icon.png"));
        assert!(entry.contains("Exec=\"/tmp/Speaky App/speaky\""));
    }

    #[test]
    fn detects_only_the_debian_binary_as_packaged() {
        assert!(is_deb_install(Path::new("/usr/bin/speaky")));
        assert!(!is_deb_install(Path::new("/tmp/speaky")));
        assert!(!is_deb_install(Path::new(
            "/workspace/speaky-tauri/src-tauri/target/release/speaky"
        )));
    }

    #[test]
    fn autostart_fields_are_replaced_without_duplicates() {
        let original = "[Desktop Entry]\nName=Speaky\nIcon=old\n";
        let updated = upsert_field(original, "Icon", "/new/icon.png");
        assert_eq!(updated.matches("Icon=").count(), 1);
        assert!(updated.contains("Icon=/new/icon.png"));
    }
}
