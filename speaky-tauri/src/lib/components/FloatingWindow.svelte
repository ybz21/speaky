<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { appState, displayText } from "../stores/app";
  import { t } from "../stores/i18n";
  import { setupEventListeners, cleanupEventListeners } from "../utils/tauri";
  import AppIconOrb from "./AppIconOrb.svelte";

  // State colors configuration
  const STATE_COLORS = {
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

<div
  class="floating-window"
  style="
    --gradient-start: {colors.gradientStart};
    --gradient-end: {colors.gradientEnd};
    --status-color: {colors.text};
  "
>
  <div class="container">
    <!-- Left: App icon with animation -->
    <div class="left-panel">
      <AppIconOrb
        audioLevel={$appState.audioLevel}
        mode={$appState.recordingState}
        appIcon={$appState.appIcon}
        animating={isAnimating}
      />
      {#if $appState.appName}
        <span class="app-name">
          {$appState.appName.length > 8
            ? $appState.appName.slice(0, 7) + "…"
            : $appState.appName}
        </span>
      {/if}
    </div>

    <!-- Right: Status and text -->
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
  </div>
</div>

<style>
  .floating-window {
    width: 500px;
    height: 88px;
    padding: 4px;
  }

  .container {
    display: flex;
    align-items: stretch;
    gap: 12px;
    height: 100%;
    padding: 4px 16px 4px 12px;
    background: linear-gradient(
      135deg,
      var(--gradient-start),
      var(--gradient-end)
    );
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
  }

  .left-panel {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    gap: 4px;
    width: 80px;
    flex-shrink: 0;
    padding-top: 2px;
  }

  .app-name {
    font-size: 9px;
    color: rgba(255, 255, 255, 0.5);
    text-align: center;
    max-width: 80px;
    height: 16px;
    line-height: 16px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .right-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    padding: 4px 0;
  }

  .status-label {
    font-size: 11px;
    font-weight: 500;
    line-height: 1.2;
  }

  .primary-text {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.9);
    word-wrap: break-word;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    line-height: 1.3;
  }

  .primary-text.partial {
    color: #ffe066;
  }

  .secondary-text {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.5);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    line-height: 1.2;
  }

  /* Spacer to push content to top */
  .right-panel::after {
    content: "";
    flex: 1;
  }
</style>
