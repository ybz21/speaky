mod listener;

pub(crate) use listener::is_supported_hotkey;
pub use listener::{
    recognize_and_deliver, register_hotkeys, start_keyboard_listener, HotkeyManager,
};
