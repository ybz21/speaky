use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct PermissionStatus {
    pub microphone: String,
    pub accessibility: String,
}

pub fn status() -> PermissionStatus {
    #[cfg(target_os = "macos")]
    {
        PermissionStatus {
            microphone: macos_microphone_status(),
            accessibility: if macos_accessibility_trusted() {
                "granted".to_string()
            } else {
                "denied".to_string()
            },
        }
    }

    #[cfg(not(target_os = "macos"))]
    {
        PermissionStatus {
            microphone: if crate::APP_STATE.recorder.read().is_some() {
                "granted".to_string()
            } else {
                "unavailable".to_string()
            },
            accessibility: "not_required".to_string(),
        }
    }
}

pub fn open_settings() -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        let permission = status();
        let url = if permission.microphone != "granted" {
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
        } else {
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        };
        std::process::Command::new("open")
            .arg(url)
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[cfg(target_os = "macos")]
#[link(name = "ApplicationServices", kind = "framework")]
extern "C" {
    fn AXIsProcessTrusted() -> bool;
}

#[cfg(target_os = "macos")]
#[link(name = "AVFoundation", kind = "framework")]
extern "C" {}

#[cfg(target_os = "macos")]
fn macos_accessibility_trusted() -> bool {
    unsafe { AXIsProcessTrusted() }
}

#[cfg(target_os = "macos")]
fn macos_microphone_status() -> String {
    use cocoa::base::{id, nil};
    use cocoa::foundation::NSString;
    use objc::{class, msg_send, sel, sel_impl};

    // AVMediaTypeAudio is the four-character media type "soun".
    unsafe {
        let media_type: id = NSString::alloc(nil).init_str("soun");
        let device_class = class!(AVCaptureDevice);
        let authorization: i64 =
            msg_send![device_class, authorizationStatusForMediaType: media_type];
        let _: () = msg_send![media_type, release];
        match authorization {
            0 => "not_determined",
            1 => "restricted",
            2 => "denied",
            3 => "granted",
            _ => "unknown",
        }
        .to_string()
    }
}
