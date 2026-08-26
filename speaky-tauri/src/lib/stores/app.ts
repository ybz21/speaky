import { writable, derived } from "svelte/store";

// App states
export type RecordingState =
  | "idle"
  | "recording"
  | "recognizing"
  | "polishing"
  | "done"
  | "error";

export interface AppState {
  recordingState: RecordingState;
  audioLevel: number;
  partialResult: string;
  finalResult: string;
  errorMessage: string;
  appName: string;
  appIcon: string | null;
}

export interface UiSnapshot {
  phase: RecordingState;
  audio_level: number;
  partial_result: string;
  final_result: string;
  error_message: string;
  app_name: string;
  app_icon: string | null;
}

const initialState: AppState = {
  recordingState: "idle",
  audioLevel: 0,
  partialResult: "",
  finalResult: "",
  errorMessage: "",
  appName: "",
  appIcon: null,
};

function createAppStore() {
  const { subscribe, set, update } = writable<AppState>(initialState);

  return {
    subscribe,

    startRecording: () =>
      update((state) => ({
        ...state,
        recordingState: "recording",
        partialResult: "",
        finalResult: "",
        errorMessage: "",
      })),

    setRecognizing: () =>
      update((state) => ({ ...state, recordingState: "recognizing" })),

    updateAudioLevel: (level: number) =>
      update((state) => ({
        ...state,
        audioLevel: Math.min(1, Math.max(0, level)),
      })),

    updatePartialResult: (text: string) =>
      update((state) => ({ ...state, partialResult: text })),

    setResult: (text: string) =>
      update((state) => ({
        ...state,
        recordingState: "done",
        finalResult: text,
        partialResult: "",
      })),

    setError: (message: string) =>
      update((state) => ({ ...state, recordingState: "error", errorMessage: message })),

    setAppInfo: (name: string, icon: string | null) =>
      update((state) => ({ ...state, appName: name, appIcon: icon })),

    applySnapshot: (snapshot: UiSnapshot) =>
      update((state) => ({
        ...state,
        recordingState: snapshot.phase,
        audioLevel: Math.min(1, Math.max(0, snapshot.audio_level)),
        partialResult: snapshot.partial_result,
        finalResult: snapshot.final_result,
        errorMessage: snapshot.error_message,
        appName: snapshot.app_name,
        appIcon: snapshot.app_icon,
      })),

    reset: () => set(initialState),

    setRecordingState: (state: RecordingState) =>
      update((s) => ({
        ...s,
        recordingState: state,
      })),
  };
}

export const appState = createAppStore();

// Helper function for direct state setting
export function setRecordingState(state: RecordingState) {
  appState.setRecordingState(state);
}

// Derived store for display text
export const displayText = derived(appState, ($state) => {
  if ($state.finalResult) return $state.finalResult;
  if ($state.partialResult) return $state.partialResult;
  if ($state.errorMessage) return $state.errorMessage;
  return "";
});
