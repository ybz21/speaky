import { invoke } from "@tauri-apps/api/core";
import { listen, type Event, type UnlistenFn } from "@tauri-apps/api/event";
import { appState, type UiSnapshot } from "../stores/app";

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
  state: "started" | "stopped" | "recognizing" | "polishing";
}

export interface AppInfoEvent {
  name: string;
  icon: string | null;
}

// IPC Commands
export async function startRecording(): Promise<void> {
  return invoke("start_recording");
}

export async function stopRecording(): Promise<void> {
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

export async function getFocusedAppInfo(): Promise<AppInfoEvent> {
  return invoke("get_focused_app_info");
}

export async function getUiState(): Promise<UiSnapshot> {
  return invoke("get_ui_state");
}

// Event listeners
let unlistenFns: UnlistenFn[] = [];

export async function setupEventListeners(): Promise<void> {
  // Clean up any existing listeners
  await cleanupEventListeners();

  // Helper to push and track listeners
  const addListener = async <T>(event: string, handler: (event: Event<T>) => void) => {
    unlistenFns.push(await listen<T>(event, handler));
  };

  // Audio level updates
  await addListener<AudioLevelEvent>("audio-level", (event) => {
    appState.updateAudioLevel(event.payload.level);
  });

  // Partial recognition results
  await addListener<PartialResultEvent>("partial-result", (event) => {
    appState.updatePartialResult(event.payload.text);
  });

  // Final recognition result
  await addListener<FinalResultEvent>("final-result", (event) => {
    appState.setResult(event.payload.text);
  });

  // Error events
  await addListener<ErrorEvent>("recognition-error", (event) => {
    appState.setError(event.payload.message);
  });

  // Recording state changes
  await addListener<RecordingStateEvent>("recording-state", async (event) => {
    switch (event.payload.state) {
      case "started":
        appState.startRecording();
        try {
          const appInfo = await getFocusedAppInfo();
          console.log("Got app info via command:", appInfo.name);
          appState.setAppInfo(appInfo.name, appInfo.icon);
        } catch (e) {
          console.error("Failed to get app info:", e);
        }
        break;
      case "recognizing":
        appState.setRecognizing();
        break;
      case "polishing":
        appState.setRecordingState("polishing");
        break;
      case "stopped":
        break;
    }
  });

  // App info updates
  await addListener<AppInfoEvent>("app-info", (event) => {
    console.log("Received app-info event:", event.payload.name);
    appState.setAppInfo(event.payload.name, event.payload.icon);
  });
}

export async function cleanupEventListeners(): Promise<void> {
  for (const unlisten of unlistenFns) {
    unlisten();
  }
  unlistenFns = [];
}
