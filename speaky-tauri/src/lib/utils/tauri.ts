import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { appState } from "../stores/app";

// Event types from Rust backend
export interface AudioLevelEvent {
  level: number;
}

export interface PartialResultEvent {
  text: string;
}

export interface FinalResultEvent {
  text: string;
}

export interface ErrorEvent {
  message: string;
}

export interface RecordingStateEvent {
  state: "started" | "stopped" | "recognizing";
}

export interface AppInfoEvent {
  name: string;
  icon: string | null;
}

// IPC Commands
export async function startRecording(): Promise<void> {
  return invoke("start_recording");
}

export async function stopRecording(): Promise<string> {
  return invoke("stop_recording");
}

export async function getAudioDevices(): Promise<Array<{ index: number; name: string }>> {
  return invoke("get_audio_devices");
}

export async function setHotkey(hotkey: string, holdTime: number): Promise<void> {
  return invoke("set_hotkey", { hotkey, holdTime });
}

export async function showWindow(): Promise<void> {
  return invoke("show_window");
}

export async function hideWindow(): Promise<void> {
  return invoke("hide_window");
}

export async function pasteText(text: string): Promise<void> {
  return invoke("paste_text", { text });
}

// Event listeners
let unlistenFns: UnlistenFn[] = [];

export async function setupEventListeners(): Promise<void> {
  // Clean up any existing listeners
  await cleanupEventListeners();

  // Audio level updates
  unlistenFns.push(
    await listen<AudioLevelEvent>("audio-level", (event) => {
      appState.updateAudioLevel(event.payload.level);
    })
  );

  // Partial recognition results
  unlistenFns.push(
    await listen<PartialResultEvent>("partial-result", (event) => {
      appState.updatePartialResult(event.payload.text);
    })
  );

  // Final recognition result
  unlistenFns.push(
    await listen<FinalResultEvent>("final-result", (event) => {
      appState.setResult(event.payload.text);
    })
  );

  // Error events
  unlistenFns.push(
    await listen<ErrorEvent>("recognition-error", (event) => {
      appState.setError(event.payload.message);
    })
  );

  // Recording state changes
  unlistenFns.push(
    await listen<RecordingStateEvent>("recording-state", (event) => {
      switch (event.payload.state) {
        case "started":
          appState.startRecording();
          break;
        case "recognizing":
          appState.setRecognizing();
          break;
        case "stopped":
          // State will be updated by final-result or error event
          break;
      }
    })
  );

  // App info updates
  unlistenFns.push(
    await listen<AppInfoEvent>("app-info", (event) => {
      appState.setAppInfo(event.payload.name, event.payload.icon);
    })
  );
}

export async function cleanupEventListeners(): Promise<void> {
  for (const unlisten of unlistenFns) {
    unlisten();
  }
  unlistenFns = [];
}
