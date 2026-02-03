use log::{debug, error, info};
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

    // Small delay before paste to ensure clipboard is ready
    std::thread::sleep(std::time::Duration::from_millis(50));

    // Simulate Ctrl+V / Cmd+V based on platform
    simulate_paste()?;
    
    debug!("Paste simulation completed");
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
                "Failed to send keyboard input".to_string()
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
        return Err(PasteError::SimulationFailed(format!("osascript error: {}", stderr)));
    }

    debug!("macOS paste simulated successfully");
    Ok(())
}

/// Simulate keyboard paste command (Ctrl+V) on Linux
#[cfg(target_os = "linux")]
fn simulate_paste() -> Result<(), PasteError> {
    use std::process::Command;

    // Try xdotool first (works on X11)
    let result = Command::new("xdotool")
        .arg("key")
        .arg("ctrl+v")
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

    // Fallback: try using ydotool for Wayland
    let result = Command::new("ydotool")
        .arg("key")
        .arg("29:1")  // Ctrl down
        .arg("47:1")  // V down
        .arg("47:0")  // V up
        .arg("29:0")  // Ctrl up
        .output();

    match result {
        Ok(output) if output.status.success() => {
            debug!("Linux paste simulated with ydotool");
            Ok(())
        }
        Ok(output) => {
            error!("ydotool failed with exit code: {:?}", output.status);
            Err(PasteError::ToolNotAvailable(
                "Neither xdotool nor ydotool is available".to_string()
            ))
        }
        Err(e) => {
            debug!("ydotool not available: {}", e);
            Err(PasteError::ToolNotAvailable(
                "Neither xdotool nor ydotool is installed".to_string()
            ))
        }
    }
}
