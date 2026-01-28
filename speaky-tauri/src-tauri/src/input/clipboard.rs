use log::info;
use tauri::AppHandle;
use tauri_plugin_clipboard_manager::ClipboardExt;

/// Write text to clipboard and simulate paste
pub fn paste_text(app: &AppHandle, text: &str) -> Result<(), String> {
    info!("Pasting text: {}...", &text.chars().take(30).collect::<String>());

    // Write to clipboard using Tauri plugin
    app.clipboard()
        .write_text(text)
        .map_err(|e| format!("Failed to write to clipboard: {}", e))?;

    // Small delay before paste
    std::thread::sleep(std::time::Duration::from_millis(50));

    // Simulate Ctrl+V / Cmd+V based on platform
    simulate_paste()?;

    Ok(())
}

#[cfg(target_os = "windows")]
fn simulate_paste() -> Result<(), String> {
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP,
        VIRTUAL_KEY, VK_CONTROL, VK_V,
    };

    unsafe {
        let mut inputs: Vec<INPUT> = Vec::with_capacity(4);

        // Press Ctrl
        inputs.push(INPUT {
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
        });

        // Press V
        inputs.push(INPUT {
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
        });

        // Release V
        inputs.push(INPUT {
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
        });

        // Release Ctrl
        inputs.push(INPUT {
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
        });

        let result = SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
        if result != inputs.len() as u32 {
            return Err("Failed to send input".to_string());
        }
    }

    Ok(())
}

#[cfg(target_os = "macos")]
fn simulate_paste() -> Result<(), String> {
    use std::process::Command;

    // Use AppleScript to simulate Cmd+V
    let output = Command::new("osascript")
        .arg("-e")
        .arg("tell application \"System Events\" to keystroke \"v\" using command down")
        .output()
        .map_err(|e| format!("Failed to run osascript: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("osascript failed: {}", stderr));
    }

    Ok(())
}

#[cfg(target_os = "linux")]
fn simulate_paste() -> Result<(), String> {
    use std::process::Command;

    // Try xdotool first, then xclip
    let result = Command::new("xdotool")
        .arg("key")
        .arg("ctrl+v")
        .output();

    match result {
        Ok(output) if output.status.success() => Ok(()),
        _ => {
            // Fallback: try using ydotool for Wayland
            let result = Command::new("ydotool")
                .arg("key")
                .arg("29:1")  // Ctrl down
                .arg("47:1")  // V down
                .arg("47:0")  // V up
                .arg("29:0")  // Ctrl up
                .output();

            match result {
                Ok(output) if output.status.success() => Ok(()),
                _ => Err("Failed to simulate paste: xdotool and ydotool not available".to_string()),
            }
        }
    }
}
