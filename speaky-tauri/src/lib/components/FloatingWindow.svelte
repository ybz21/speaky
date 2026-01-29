<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { appState, displayText, setRecordingState } from "../stores/app";
  import { t } from "../stores/i18n";
  import { setupEventListeners, cleanupEventListeners, startRecording, stopRecording } from "../utils/tauri";
  import AppIconOrb from "./AppIconOrb.svelte";

  // Development mode detection
  const isDev = import.meta.env.DEV;
  let isTestRecording = false;

  async function handleTestRecord() {
    if (isTestRecording) {
      // Stop recording
      isTestRecording = false;
      setRecordingState("recognizing");
      try {
        await stopRecording();
      } catch (e) {
        console.error("Stop recording error:", e);
      }
    } else {
      // Start recording
      isTestRecording = true;
      setRecordingState("recording");
      try {
        await startRecording();
      } catch (e) {
        console.error("Start recording error:", e);
      }
    }
  }

  // State colors - matching Python version exactly
  const STATE_COLORS: Record<string, {
    text: string;
    gradientStart: string;
    gradientEnd: string;
  }> = {
    recording: {
      text: "#00D9FF",
      gradientStart: "rgba(0, 180, 220, 0.10)",
      gradientEnd: "rgba(15, 25, 35, 0.95)",
    },
    recognizing: {
      text: "#FFB84D",
      gradientStart: "rgba(255, 150, 50, 0.10)",
      gradientEnd: "rgba(35, 25, 15, 0.95)",
    },
    done: {
      text: "#00E676",
      gradientStart: "rgba(0, 200, 100, 0.10)",
      gradientEnd: "rgba(15, 30, 20, 0.95)",
    },
    error: {
      text: "#FF5252",
      gradientStart: "rgba(255, 80, 80, 0.10)",
      gradientEnd: "rgba(35, 15, 15, 0.95)",
    },
    idle: {
      text: "#666666",
      gradientStart: "rgba(50, 50, 50, 0.10)",
      gradientEnd: "rgba(20, 20, 25, 0.95)",
    },
  };

  function getStatusText(state: string, trans: (key: string) => string): string {
    switch (state) {
      case "recording":
        return trans("listening");
      case "recognizing":
        return trans("recognizing");
      case "done":
        return trans("done");
      case "error":
        return trans("error");
      default:
        return "";
    }
  }

  function formatResultText(text: string): { primary: string; secondary: string } {
    if (!text) return { primary: "", secondary: "" };

    const trimmed = text.trim();
    if (trimmed.length <= 30) return { primary: trimmed, secondary: "" };

    const lines = trimmed.split("\n").filter((l) => l.trim());
    if (lines.length === 1) {
      const sentences = trimmed.split("。");
      if (sentences.length > 1 && sentences[0]) {
        const primary = sentences[0] + "。";
        const rest = sentences.slice(1).join("。").trim();
        const secondary = rest.length > 40 ? rest.slice(0, 40) + "..." : rest;
        return { primary, secondary };
      }
      return { primary: trimmed.slice(0, 30) + "...", secondary: "" };
    }

    let primary = lines[0];
    if (primary.length > 40) primary = primary.slice(0, 37) + "...";

    let secondary = "";
    if (lines.length === 2) {
      secondary = lines[1].length > 40 ? lines[1].slice(0, 40) + "..." : lines[1];
    } else {
      secondary = `共 ${lines.length} 项内容`;
    }

    return { primary, secondary };
  }

  $: colors = STATE_COLORS[$appState.recordingState] || STATE_COLORS.idle;
  $: statusText = getStatusText($appState.recordingState, $t);
  $: formattedText = formatResultText($displayText);
  $: isAnimating =
    $appState.recordingState === "recording" ||
    $appState.recordingState === "recognizing";

  onMount(async () => {
    await setupEventListeners();
  });

  onDestroy(async () => {
    await cleanupEventListeners();
  });
</script>

<div class="floating-window">
  <div
    class="container"
    style="
      background: linear-gradient(135deg, {colors.gradientStart}, {colors.gradientEnd});
    "
  >
    <!-- Left panel: App icon + name -->
    <div class="left-panel">
      <AppIconOrb
        audioLevel={$appState.audioLevel}
        mode={$appState.recordingState}
        appIcon={$appState.appIcon}
        animating={isAnimating}
      />
      <div class="app-name">
        {#if $appState.appName}
          {$appState.appName.length > 8
            ? $appState.appName.slice(0, 7) + "…"
            : $appState.appName}
        {/if}
      </div>
    </div>

    <!-- Right panel: Status + Text -->
    <div class="right-panel">
      <div class="status-label" style="color: {colors.text}">
        {statusText}
      </div>
      <div
        class="primary-text"
        class:partial={$appState.recordingState === "recognizing"}
      >
        {formattedText.primary}
      </div>
      {#if formattedText.secondary}
        <div class="secondary-text">{formattedText.secondary}</div>
      {/if}
    </div>

    <!-- Dev mode test button -->
    {#if isDev}
      <button class="dev-test-btn" on:click={handleTestRecord}>
        {isTestRecording ? "⏹" : "🎤"}
      </button>
    {/if}
  </div>
</div>

<style>
  /* Window: 500x88px with 4px padding for shadow space */
  .floating-window {
    width: 500px;
    height: 88px;
    padding: 4px;
    box-sizing: border-box;
  }

  /* Container: fills window minus padding, with gradient background */
  .container {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: row;
    align-items: stretch;
    padding: 4px 16px 4px 12px;
    gap: 12px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    box-sizing: border-box;
  }

  /* Left panel: 80px width, icon + app name stacked */
  .left-panel {
    width: 80px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding-top: 2px;
    gap: 4px;
  }

  /* App name: 9pt, 16px height, centered */
  .app-name {
    width: 80px;
    height: 16px;
    font-size: 9pt;
    line-height: 16px;
    color: rgba(255, 255, 255, 0.5);
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    background: transparent;
  }

  /* Right panel: fills remaining space, content stacked top */
  .right-panel {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: flex-start;
    padding: 4px 0;
    gap: 2px;
  }

  /* Status label: 11pt, medium weight */
  .status-label {
    font-size: 11pt;
    font-weight: 500;
    line-height: 1.3;
    background: transparent;
  }

  /* Primary text: 13pt, white 90% */
  .primary-text {
    font-size: 13pt;
    color: rgba(255, 255, 255, 0.9);
    line-height: 1.3;
    word-wrap: break-word;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    background: transparent;
  }

  /* Partial result: yellow text */
  .primary-text.partial {
    color: #FFE066;
  }

  /* Secondary text: 11pt, white 50% */
  .secondary-text {
    font-size: 11pt;
    color: rgba(255, 255, 255, 0.5);
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    background: transparent;
  }

  /* Dev mode test button */
  .dev-test-btn {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    width: 36px;
    height: 36px;
    border: none;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.1);
    color: white;
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
  }

  .dev-test-btn:hover {
    background: rgba(255, 255, 255, 0.2);
  }

  .container {
    position: relative;
  }
</style>
