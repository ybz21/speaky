use log::{debug, error, info};
#[cfg(target_os = "linux")]
use once_cell::sync::OnceCell;
#[cfg(target_os = "linux")]
use std::io::Write;
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
    paste_text_to_window(app, text, None)
}

/// Write text to the clipboard and paste it into a known target window.
///
/// On a Wayland desktop an application can still be an XWayland client.  In
/// that case the desktop portal may accept the keyboard request without the
/// XWayland client ever receiving it.  A captured X11 window id lets us send
/// Ctrl+V directly to that client instead.
pub fn paste_text_to_window(
    app: &AppHandle,
    text: &str,
    target_window_id: Option<&str>,
) -> Result<(), PasteError> {
    let preview = if text.len() > 30 {
        format!("{}...", &text.chars().take(30).collect::<String>())
    } else {
        text.to_string()
    };
    info!("Pasting text: {}", preview);

    // Native Wayland clients cannot reliably read the X11 selection.  The
    // clipboard manager plugin uses X11 when GNOME's data-control protocol is
    // unavailable, so prefer wl-copy on Wayland.  It creates a proper
    // Wayland data offer and keeps serving the selection after this call.
    #[cfg(target_os = "linux")]
    let clipboard_written = if std::env::var_os("WAYLAND_DISPLAY").is_some() {
        write_wayland_clipboard(text).unwrap_or(false)
    } else {
        false
    };

    #[cfg(not(target_os = "linux"))]
    let clipboard_written = false;

    if !clipboard_written {
        // Write to clipboard using Tauri plugin (X11 and non-Linux fallback).
        app.clipboard()
            .write_text(text)
            .map_err(|e| PasteError::ClipboardWriteFailed(e.to_string()))?;
    }

    debug!("Text written to clipboard");

    #[cfg(target_os = "linux")]
    if std::env::var_os("WAYLAND_DISPLAY").is_some() {
        // uinput events enter the compositor through the same path as a real
        // keyboard. This works for both native Wayland and XWayland clients
        // and avoids false-success responses from desktop portal injection.
        std::thread::sleep(std::time::Duration::from_millis(80));
        match uinput_paste() {
            Ok(()) => {
                info!("Paste shortcut emitted through the virtual keyboard");
                return Ok(());
            }
            Err(error) => {
                error!("Virtual keyboard paste failed: {error}; falling back");
            }
        }
    }

    #[cfg(target_os = "linux")]
    if let Some(window_id) = target_window_id.filter(|id| !id.is_empty() && *id != "0x0") {
        // Give both the Wayland clipboard bridge and the restored target
        // focus a moment to settle before delivering the shortcut.
        std::thread::sleep(std::time::Duration::from_millis(80));
        match simulate_x11_window_paste(window_id) {
            Ok(()) => {
                info!("Paste shortcut sent directly to XWayland window {window_id}");
                return Ok(());
            }
            Err(error) => {
                error!("Direct paste to XWayland window {window_id} failed: {error}; falling back");
            }
        }
    }

    // Native Wayland applications (including Ubuntu Chrome) do not accept
    // XTest events. GNOME's RemoteDesktop portal is the supported way for a
    // desktop app to inject Ctrl+V after the user grants access.
    #[cfg(target_os = "linux")]
    if std::env::var_os("WAYLAND_DISPLAY").is_some() {
        match portal_paste() {
            Ok(()) => return Ok(()),
            Err(error) => {
                error!("GNOME RemoteDesktop paste failed: {}", error);
            }
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
fn simulate_x11_window_paste(window_id: &str) -> Result<(), PasteError> {
    use std::process::Command;

    let output = Command::new("xdotool")
        .args(["key", "--window", window_id, "--clearmodifiers", "ctrl+v"])
        .output()
        .map_err(|error| PasteError::ToolNotAvailable(error.to_string()))?;

    if output.status.success() {
        Ok(())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        Err(PasteError::SimulationFailed(if stderr.is_empty() {
            format!("xdotool exited with {}", output.status)
        } else {
            stderr
        }))
    }
}

#[cfg(target_os = "linux")]
fn write_wayland_clipboard(text: &str) -> Result<bool, String> {
    use std::process::{Command, Stdio};

    let mut child = match Command::new("wl-copy")
        .args(["--type", "text/plain;charset=utf-8"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        // wl-copy forks a background process that owns the clipboard. If its
        // stderr is piped, the background process keeps that pipe open and
        // wait_with_output never returns until another clipboard owner
        // replaces it. Inherit no pipes so we only wait for the short-lived
        // launcher process.
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => child,
        Err(error) => {
            debug!("wl-copy not available: {}", error);
            return Ok(false);
        }
    };

    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(text.as_bytes())
            .map_err(|error| format!("failed to write wl-copy input: {}", error))?;
    }
    let status = child
        .wait()
        .map_err(|error| format!("failed to wait for wl-copy: {}", error))?;
    if status.success() {
        info!("Text written through the native Wayland clipboard");
        Ok(true)
    } else {
        debug!("wl-copy failed with status: {status}");
        Ok(false)
    }
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
static UINPUT_KEYBOARD: OnceCell<std::sync::Mutex<evdev::uinput::VirtualDevice>> = OnceCell::new();

#[cfg(target_os = "linux")]
fn get_uinput_keyboard() -> Result<
    (
        &'static std::sync::Mutex<evdev::uinput::VirtualDevice>,
        bool,
    ),
    PasteError,
> {
    use evdev::{uinput::VirtualDevice, AttributeSet, KeyCode};

    let mut created = false;
    let keyboard = UINPUT_KEYBOARD.get_or_try_init(|| {
        let mut keys = AttributeSet::<KeyCode>::new();
        keys.insert(KeyCode::KEY_LEFTCTRL);
        keys.insert(KeyCode::KEY_V);
        let device = VirtualDevice::builder()
            .and_then(|builder| builder.with_keys(&keys))
            .and_then(|builder| builder.name("Speaky Virtual Keyboard").build())
            .map_err(|error| PasteError::ToolNotAvailable(error.to_string()))?;
        created = true;
        Ok::<_, PasteError>(std::sync::Mutex::new(device))
    })?;

    Ok((keyboard, created))
}

/// Create the Wayland virtual keyboard before the evdev hotkey listener starts.
///
/// rdev watches `/dev/input` for hot-plugged devices and opens a new event node
/// immediately. udev applies the active-user ACL slightly later, so creating
/// this device during the first paste races with rdev and terminates the hotkey
/// listener with `PermissionDenied`. Preparing it during app startup removes
/// that race and lets rdev include it in its initial device set.
#[cfg(target_os = "linux")]
pub fn prepare_paste_input() -> Result<(), PasteError> {
    if std::env::var_os("WAYLAND_DISPLAY").is_none() {
        return Ok(());
    }

    let (_, created) = get_uinput_keyboard()?;
    if created {
        std::thread::sleep(std::time::Duration::from_millis(300));
        info!("Wayland virtual keyboard prepared before hotkey listener");
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn uinput_paste() -> Result<(), PasteError> {
    use evdev::{EventType, InputEvent, KeyCode};

    let (keyboard, created) = get_uinput_keyboard()?;
    // This is normally initialized during app setup. Keep the delay here for
    // direct command/test callers that invoke paste without normal startup.
    if created {
        std::thread::sleep(std::time::Duration::from_millis(300));
    }

    let mut keyboard = keyboard
        .lock()
        .map_err(|_| PasteError::SimulationFailed("virtual keyboard lock poisoned".to_string()))?;
    let key_event = |key: KeyCode, value| InputEvent::new(EventType::KEY.0, key.code(), value);

    keyboard
        .emit(&[key_event(KeyCode::KEY_LEFTCTRL, 1)])
        .map_err(|error| PasteError::SimulationFailed(error.to_string()))?;
    std::thread::sleep(std::time::Duration::from_millis(10));
    let press_result = keyboard.emit(&[key_event(KeyCode::KEY_V, 1)]);
    std::thread::sleep(std::time::Duration::from_millis(20));
    let release_v_result = keyboard.emit(&[key_event(KeyCode::KEY_V, 0)]);
    let release_ctrl_result = keyboard.emit(&[key_event(KeyCode::KEY_LEFTCTRL, 0)]);

    press_result
        .and(release_v_result)
        .and(release_ctrl_result)
        .map_err(|error| PasteError::SimulationFailed(error.to_string()))?;
    Ok(())
}

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
        DeviceType, KeyState, NotifyKeyboardKeysymOptions, RemoteDesktop, SelectDevicesOptions,
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
    // NotifyKeyboardKeysym takes X11 keysym values, not Linux evdev
    // keycodes.  Using evdev values (29/47) appears to succeed on D-Bus but
    // produces unrelated keys in GNOME/Chrome.  Ctrl_L and lowercase `v`
    // are stable across keyboard layouts and Wayland clients.
    portal
        .proxy
        .notify_keyboard_keysym(
            &portal.session,
            0xffe3,
            KeyState::Pressed,
            NotifyKeyboardKeysymOptions::default(),
        )
        .await
        .map_err(|error| error.to_string())?;
    portal
        .proxy
        .notify_keyboard_keysym(
            &portal.session,
            0x76,
            KeyState::Pressed,
            NotifyKeyboardKeysymOptions::default(),
        )
        .await
        .map_err(|error| error.to_string())?;
    portal
        .proxy
        .notify_keyboard_keysym(
            &portal.session,
            0x76,
            KeyState::Released,
            NotifyKeyboardKeysymOptions::default(),
        )
        .await
        .map_err(|error| error.to_string())?;
    portal
        .proxy
        .notify_keyboard_keysym(
            &portal.session,
            0xffe3,
            KeyState::Released,
            NotifyKeyboardKeysymOptions::default(),
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
