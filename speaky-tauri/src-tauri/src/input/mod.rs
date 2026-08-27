mod clipboard;

#[cfg(target_os = "linux")]
pub use clipboard::prepare_paste_input;
pub use clipboard::{paste_text, paste_text_to_window};
