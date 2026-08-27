use log::{debug, error, info};
#[cfg(target_os = "linux")]
use once_cell::sync::OnceCell;
use tauri::AppHandle;
use tauri_plugin_clipboard_manager::ClipboardExt;

/// Errors that can occur during paste operations
#[derive(Debug, Clone, PartialEq)]
pub enum PasteError {
    /// Failed to write text to clipboard
    ClipboardWriteFailed(String),

    /// Failed to simulate keyboard input
    SimulationFailed(String),

    /// Required tool not available
    ToolNotAvailable(String),

    /// Unknown error
    Unknown(String),
}

impl std::fmt::Display for PasteError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PasteError::ClipboardWriteFailed(msg) => write!(f, "Clipboard write failed: {}", msg),
            PasteError::SimulationFailed(msg) => write!(f, "Paste simulation failed: {}", msg),
            PasteError::ToolNotAvailable(msg) => write!(f, "Tool not available: {}", msg),
            PasteError::Unknown(msg) => write!(f, "Unknown error: {}", msg),
        }
    }
}

impl std::error::Error for PasteError {}

/// Write text to clipboard and simulate paste
///
/// This function writes the provided text to the system clipboard and then
/// simulates the appropriate keyboard shortcut (Ctrl+V or Cmd+V) to paste
/// the text into the currently focused application.
///
/// # Arguments
/// * `app` - Tauri application handle
/// * `text` - Text to paste
///
/// # Returns
/// Result indicating success or error
pub fn paste_text(app: &AppHandle, text: &str) -> Result<(), PasteError> {
    let preview = if text.len() > 30 {
        format!("{}...", &text.chars().take(30).collect::<String>())
    } else {
        text.to_string()
    };
    info!("Pasting text: {}", preview);

    // Write to clipboard using Tauri plugin
    app.clipboard()
        .write_text(text)
        .map_err(|e| PasteError::ClipboardWriteFailed(e.to_string()))?;

    debug!("Text written to clipboard");

    // Native Wayland applications (including Ubuntu Chrome) do not accept
    // XTest events. GNOME's RemoteDesktop portal is the supported way for a
    // desktop app to inject Ctrl+V after the user grants access.
    #[cfg(target_os = "linux")]
    if std::env::var_os("WAYLAND_DISPLAY").is_some() {
        if portal_paste().is_ok() {
            return Ok(());
        }
        // wtype is useful on compositors that expose virtual-keyboard; GNOME
        // currently does not, so keep it as a best-effort fallback.
        if let Ok(output) = std::process::Command::new("wtype").arg(text).output() {
            if output.status.success() {
                info!("Text typed successfully through Wayland");
                return Ok(());
            }
        }
    }

    // Small delay before paste to ensure clipboard is ready
    std::thread::sleep(std::time::Duration::from_millis(50));

    // Simulate Ctrl+V / Cmd+V based on platform
    simulate_paste()?;

    debug!("Paste simulation completed");
    Ok(())
}

#[cfg(target_os = "linux")]
enum PortalCommand {
    Paste(std::sync::mpsc::Sender<Result<(), String>>),
}

#[cfg(target_os = "linux")]
struct PortalState {
    proxy: ashpd::desktop::remote_desktop::RemoteDesktop,
    session: ashpd::desktop::Session<ashpd::desktop::remote_desktop::RemoteDesktop>,
}

#[cfg(target_os = "linux")]
static PORTAL_COMMANDS: OnceCell<std::sync::mpsc::Sender<PortalCommand>> = OnceCell::new();

#[cfg(target_os = "linux")]
fn portal_paste() -> Result<(), PasteError> {
    let sender = PORTAL_COMMANDS.get_or_init(|| {
        let (sender, receiver) = std::sync::mpsc::channel::<PortalCommand>();
        std::thread::Builder::new()
            .name("speaky-wayland-portal".to_string())
            .spawn(move || {
                let runtime = match tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .build()
                {
                    Ok(runtime) => runtime,
                    Err(error) => {
                        error!("Failed to create Wayland portal runtime: {}", error);
                        return;
                    }
                };
                let mut state: Option<PortalState> = None;
                while let Ok(command) = receiver.recv() {
                    let PortalCommand::Paste(result_sender) = command;
                    let result = runtime.block_on(portal_send_paste(&mut state));
                    let _ = result_sender.send(result);
                }
            })
            .expect("failed to start Wayland portal thread");
        sender
    });

    let (result_sender, result_receiver) = std::sync::mpsc::channel();
    sender
        .send(PortalCommand::Paste(result_sender))
        .map_err(|error| PasteError::SimulationFailed(error.to_string()))?;
    match result_receiver.recv() {
        Ok(Ok(())) => Ok(()),
        Ok(Err(error)) => Err(PasteError::SimulationFailed(error)),
        Err(error) => Err(PasteError::SimulationFailed(error.to_string())),
    }
}

#[cfg(target_os = "linux")]
async fn portal_send_paste(state: &mut Option<PortalState>) -> Result<(), String> {
    use ashpd::desktop::remote_desktop::{
        DeviceType, KeyState, NotifyKeyboardKeycodeOptions, RemoteDesktop, SelectDevicesOptions,
    };
    use ashpd::desktop::PersistMode;
    use enumflags2::BitFlags;

    if state.is_none() {
        let proxy = RemoteDesktop::new()
            .await
            .map_err(|error| error.to_string())?;
        let session = proxy
            .create_session(Default::default())
            .await
            .map_err(|error| error.to_string())?;
        proxy
            .select_devices(
                &session,
                SelectDevicesOptions::default()
                    .set_devices(BitFlags::from_flag(DeviceType::Keyboard))
                    .set_persist_mode(PersistMode::Application),
            )
            .await
            .map_err(|error| error.to_string())?
            .response()
            .map_err(|error| error.to_string())?;
        proxy
            .start(&session, None, Default::default())
            .await
            .map_err(|error| error.to_string())?
            .response()
            .map_err(|error| error.to_string())?;
        *state = Some(PortalState { proxy, session });
    }

    let portal = state.as_ref().expect("portal state initialized");
    portal
        .proxy
        .notify_keyboard_keycode(
            &portal.session,
            29,
            KeyState::Pressed,
            NotifyKeyboardKeycodeOptions::default(),
        )
        .await
        .map_err(|error| error.to_string())?;
    portal
        .proxy
        .notify_keyboard_keycode(
            &portal.session,
            47,
            KeyState::Pressed,
            NotifyKeyboardKeycodeOptions::default(),
        )
        .await
        .map_err(|error| error.to_string())?;
    portal
        .proxy
        .notify_keyboard_keycode(
            &portal.session,
            47,
            KeyState::Released,
            NotifyKeyboardKeycodeOptions::default(),
        )
        .await
        .map_err(|error| error.to_string())?;
    portal
        .proxy
        .notify_keyboard_keycode(
            &portal.session,
            29,
            KeyState::Released,
            NotifyKeyboardKeycodeOptions::default(),
        )
        .await
        .map_err(|error| error.to_string())?;
    Ok(())
}

/// Simulate keyboard paste command (Ctrl+V / Cmd+V)
#[cfg(target_os = "windows")]
fn simulate_paste() -> Result<(), PasteError> {
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP,
        VIRTUAL_KEY, VK_CONTROL, VK_V,
    };

    unsafe {
        let inputs = [
            // Press Ctrl
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_CONTROL,
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            // Press V
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_V,
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            // Release V
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_V,
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            // Release Ctrl
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_CONTROL,
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
        ];

        let result = SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
        if result != inputs.len() as u32 {
            error!("SendInput failed, returned {}", result);
            return Err(PasteError::SimulationFailed(
                "Failed to send keyboard input".to_string(),
            ));
        }
    }

    debug!("Windows paste simulated successfully");
    Ok(())
}

/// Simulate keyboard paste command (Cmd+V) on macOS
#[cfg(target_os = "macos")]
fn simulate_paste() -> Result<(), PasteError> {
    use std::process::Command;

    // Use AppleScript to simulate Cmd+V
    let output = Command::new("osascript")
        .arg("-e")
        .arg("tell application \"System Events\" to keystroke \"v\" using command down")
        .output()
        .map_err(|e| PasteError::SimulationFailed(format!("Failed to run osascript: {}", e)))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        error!("osascript failed: {}", stderr);
        return Err(PasteError::SimulationFailed(format!(
            "osascript error: {}",
            stderr
        )));
    }

    debug!("macOS paste simulated successfully");
    Ok(())
}

/// Simulate keyboard paste command (Ctrl+V) on Linux
#[cfg(target_os = "linux")]
fn simulate_paste() -> Result<(), PasteError> {
    use std::process::Command;

    // Try xdotool on X11. On a native Wayland session xdotool can report
    // success while sending the event only to an unrelated Xwayland window,
    // which makes paste appear successful in logs but not in the browser.
    if std::env::var_os("WAYLAND_DISPLAY").is_none() {
        let result = Command::new("xdotool")
            .args(["key", "--clearmodifiers", "ctrl+v"])
            .output();

        match result {
            Ok(output) if output.status.success() => {
                debug!("Linux paste simulated with xdotool");
                return Ok(());
            }
            Ok(output) => {
                error!("xdotool failed with exit code: {:?}", output.status);
            }
            Err(e) => {
                debug!("xdotool not available: {}", e);
            }
        }
    }

    // Fallback: try using ydotool for Wayland
    let result = Command::new("ydotool")
        .arg("key")
        .arg("29:1") // Ctrl down
        .arg("47:1") // V down
        .arg("47:0") // V up
        .arg("29:0") // Ctrl up
        .output();

    match result {
        Ok(output) if output.status.success() => {
            debug!("Linux paste simulated with ydotool");
            Ok(())
        }
        Ok(output) => {
            error!("ydotool failed with exit code: {:?}", output.status);
            Err(PasteError::ToolNotAvailable(
                "Wayland paste requires wtype or ydotool".to_string(),
            ))
        }
        Err(e) => {
            debug!("ydotool not available: {}", e);
            Err(PasteError::ToolNotAvailable(
                "Wayland paste requires wtype or ydotool".to_string(),
            ))
        }
    }
}
