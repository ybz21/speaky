<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";
  import { listen, type UnlistenFn } from "@tauri-apps/api/event";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { config, type Config, defaultConfig } from "../stores/config";
  import {
    t,
    locale,
    normalizeLocale,
    supportedLocales,
  } from "../stores/i18n";
  import DiagnosticsDialog from "./DiagnosticsDialog.svelte";
  import HistoryPanel from "./HistoryPanel.svelte";
  import {
    cancelHotkeyCapture,
    getAudioDevices,
    startHotkeyCapture,
  } from "../utils/tauri";
  import logoUrl from "../../../../resources/icon.svg?url";

  let localConfig: Config = JSON.parse(JSON.stringify(defaultConfig));
  let settingsLoaded = false;
  let saving = false;
  let validationError = "";
  let activeTab: "general" | "history" | "diagnostics" = "general";
  let contentElement: HTMLElement;
  let capturingHotkey = false;
  let hotkeyCaptureMessage = "";
  let captureTimer: ReturnType<typeof setTimeout> | undefined;
  let captureListeners: UnlistenFn[] = [];
  let audioDevices: Array<{ index: number; name: string }> = [];
  let showRecognitionApiKey = false;
  let showPolishApiKey = false;

  const quickHotkeys = ["ctrl", "alt", "shift", "cmd", "fn", "f8"];
  const engineOptions = ["volc_bigmodel", "openai"] as const;
  const polishModelOptions = [
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4o",
    "deepseek-chat",
    "qwen-plus",
    "doubao-seed-1-6-flash-250828",
  ];

  onMount(async () => {
    try {
      captureListeners = await Promise.all([
        listen<{ hotkey: string }>("hotkey-captured", ({ payload }) => {
          setLocalHotkey(payload.hotkey);
          capturingHotkey = false;
          hotkeyCaptureMessage = "";
          clearCaptureTimer();
        }),
        listen("hotkey-capture-error", () => {
          hotkeyCaptureMessage = $t("settings.hotkeyUnsupported");
        }),
      ]);
    } catch (error) {
      console.error("Failed to register hotkey capture events:", error);
      hotkeyCaptureMessage = $t("settings.hotkeyUnavailable");
    }

    const loadedConfig = await config.load();
    if (!loadedConfig) {
      validationError = $t("settings.loadFailed");
      return;
    }
    localConfig = JSON.parse(JSON.stringify(loadedConfig));
    localConfig.core.asr.audio_device_name ??= null;
    localConfig.appearance.ui_language = normalizeLocale(
      localConfig.appearance.ui_language,
    );
    locale.setLocale(localConfig.appearance.ui_language);
    try {
      audioDevices = await getAudioDevices();
    } catch (error) {
      console.error("Failed to load audio devices:", error);
      audioDevices = [];
    }
    settingsLoaded = true;
  });

  onDestroy(() => {
    clearCaptureTimer();
    captureListeners.forEach((unlisten) => unlisten());
    void cancelHotkeyCapture();
  });

  function clearCaptureTimer() {
    if (captureTimer) clearTimeout(captureTimer);
    captureTimer = undefined;
  }

  function displayHotkey(value: string): string {
    const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);
    const systemKey = isMac ? "⌘ Command" : "⊞ Win";
    const labels: Record<string, string> = {
      ctrl: "Ctrl",
      control: "Ctrl",
      ctrl_l: "Ctrl · L",
      ctrl_r: "Ctrl · R",
      alt: isMac ? "⌥ Option" : "Alt",
      alt_l: isMac ? "⌥ Option · L" : "Alt · L",
      alt_r: isMac ? "⌥ Option · R" : "Alt · R",
      shift: "⇧ Shift",
      shift_l: "⇧ Shift · L",
      shift_r: "⇧ Shift · R",
      cmd: systemKey,
      super: systemKey,
      meta: systemKey,
      cmd_l: `${systemKey} · L`,
      cmd_r: `${systemKey} · R`,
      fn: "Fn",
      space: "Space",
      tab: "Tab",
      caps_lock: "Caps Lock",
      scroll_lock: "Scroll Lock",
      num_lock: "Num Lock",
      print_screen: "Print Screen",
      backquote: "`",
      escape: "Esc",
      enter: "Enter",
      backspace: "Backspace",
      delete: "Delete",
      page_up: "Page Up",
      page_down: "Page Down",
      arrow_up: "↑",
      arrow_down: "↓",
      arrow_left: "←",
      arrow_right: "→",
    };
    if (labels[value]) return labels[value];
    if (/^f\d{1,2}$/.test(value)) return value.toUpperCase();
    if (value.length === 1) return value.toUpperCase();
    if (value.startsWith("numpad_")) return `Num ${value.slice(7).replaceAll("_", " ")}`;
    return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  // Replace the nested config object so Svelte reliably propagates captured
  // hotkeys into the save snapshot and updates the button state immediately.
  function setLocalHotkey(hotkey: string) {
    localConfig = {
      ...localConfig,
      core: {
        ...localConfig.core,
        asr: {
          ...localConfig.core.asr,
          hotkey,
        },
      },
    };
  }

  async function toggleHotkeyCapture() {
    if (!settingsLoaded) return;
    hotkeyCaptureMessage = "";
    if (capturingHotkey) {
      capturingHotkey = false;
      clearCaptureTimer();
      await cancelHotkeyCapture();
      return;
    }

    try {
      await startHotkeyCapture();
      capturingHotkey = true;
      captureTimer = setTimeout(async () => {
        capturingHotkey = false;
        hotkeyCaptureMessage = $t("settings.hotkeyTimeout");
        await cancelHotkeyCapture();
      }, 12000);
    } catch (error) {
      console.error("Failed to start hotkey capture:", error);
      hotkeyCaptureMessage = $t("settings.hotkeyUnavailable");
    }
  }

  async function chooseQuickHotkey(hotkey: string) {
    if (!settingsLoaded) return;
    capturingHotkey = false;
    hotkeyCaptureMessage = "";
    clearCaptureTimer();
    await cancelHotkeyCapture();
    setLocalHotkey(hotkey);
  }

  async function refreshAudioDevices() {
    try {
      audioDevices = await getAudioDevices();
    } catch (error) {
      console.error("Failed to refresh audio devices:", error);
    }
  }

  function selectUiLanguage(value: string) {
    localConfig.appearance.ui_language = normalizeLocale(value);
    locale.setLocale(localConfig.appearance.ui_language);
  }

  async function selectTab(tab: "general" | "history" | "diagnostics") {
    activeTab = tab;
    await tick();
    contentElement?.scrollTo({ top: 0 });
  }

  async function handleSave() {
    if (!settingsLoaded) return;
    saving = true;
    validationError = "";
    try {
      await cancelHotkeyCapture();
      capturingHotkey = false;
      clearCaptureTimer();
      const normalizedConfig: Config = JSON.parse(JSON.stringify(localConfig));
      console.info("Saving hotkey:", normalizedConfig.core.asr.hotkey);
      normalizedConfig.llm.openai.base_url = normalizedConfig.llm.openai.base_url.trim();
      normalizedConfig.llm.openai.api_key = normalizedConfig.llm.openai.api_key.trim();
      normalizedConfig.llm.openai.model = normalizedConfig.llm.openai.model.trim();
      if (
        normalizedConfig.core.asr.llm_polish &&
        (!normalizedConfig.llm.openai.base_url ||
          !normalizedConfig.llm.openai.api_key ||
          !normalizedConfig.llm.openai.model)
      ) {
        validationError = $t("settings.polishRequired");
        await selectTab("general");
        return;
      }
      const rawSelectedDevice = normalizedConfig.core.asr.audio_device as
        | number
        | string
        | null
        | undefined;
      const hasSelectedDevice =
        rawSelectedDevice !== "" &&
        rawSelectedDevice !== null &&
        rawSelectedDevice !== undefined;
      const selectedDevice = Number(rawSelectedDevice);
      const selectedDeviceName = hasSelectedDevice
        ? audioDevices.find((device) => device.index === selectedDevice)?.name
        : undefined;
      if (selectedDeviceName) {
        normalizedConfig.core.asr.audio_device_name = selectedDeviceName;
      } else if (!hasSelectedDevice || Number.isNaN(selectedDevice)) {
        normalizedConfig.core.asr.audio_device_name = null;
      }
      normalizedConfig.core.asr.audio_device =
        !hasSelectedDevice || Number.isNaN(selectedDevice) ? null : selectedDevice;

      // Recognition language is intentionally automatic and no longer exposed.
      normalizedConfig.core.asr.language = "auto";
      normalizedConfig.core.asr.streaming_mode = true;
      normalizedConfig.appearance.theme = "light";
      await config.save(normalizedConfig);

      await getCurrentWindow().hide();
    } catch (error) {
      console.error("Failed to save config:", error);
    } finally {
      saving = false;
    }
  }

  async function handleCancel() {
    await cancelHotkeyCapture();
    capturingHotkey = false;
    clearCaptureTimer();
    await getCurrentWindow().hide();
  }
</script>

<div class="settings-dialog">
  <header>
    <div class="brand">
      <img src={logoUrl} alt="" />
      <div>
        <h1>{$t("settings.title")}</h1>
        <p>{$t("settings.subtitle")}</p>
      </div>
    </div>
    <nav aria-label={$t("settings.navigation")}>
      <button class:active={activeTab === "general"} on:click={() => selectTab("general")}>
        {$t("settings.tab.general")}
      </button>
      <button class:active={activeTab === "history"} on:click={() => selectTab("history")}>
        {$t("settings.tab.history")}
      </button>
      <button class:active={activeTab === "diagnostics"} on:click={() => selectTab("diagnostics")}>
        {$t("settings.tab.diagnostics")}
      </button>
    </nav>
  </header>

  <main bind:this={contentElement} class:tool-page={activeTab !== "general"}>
    {#if activeTab === "general"}
      <section>
        <h2>{$t("settings.group.trigger")}</h2>
        <div class="panel">
          <label class="hotkey-row">
            <span>
              {$t("settings.hotkey")}
              <small>{$t("settings.hotkeyHint")}</small>
            </span>
            <div class="hotkey-control">
              <button
                type="button"
                class="hotkey-recorder"
                class:capturing={capturingHotkey}
                aria-pressed={capturingHotkey}
                disabled={!settingsLoaded}
                on:click={toggleHotkeyCapture}
              >
                <kbd>{capturingHotkey ? "…" : displayHotkey(localConfig.core.asr.hotkey)}</kbd>
                <em>
                  {capturingHotkey
                    ? $t("settings.hotkeyRecording")
                    : $t("settings.hotkeyChange")}
                </em>
              </button>
              <div class="quick-hotkeys" aria-label={$t("settings.hotkeyQuickChoices")}>
                {#each quickHotkeys as hotkey}
                  <button
                    type="button"
                    class:active={localConfig.core.asr.hotkey === hotkey}
                    disabled={!settingsLoaded}
                    on:click={() => chooseQuickHotkey(hotkey)}
                  >
                    {displayHotkey(hotkey)}
                  </button>
                {/each}
              </div>
              {#if hotkeyCaptureMessage}
                <small class="capture-message">{hotkeyCaptureMessage}</small>
              {:else}
                <small class="fn-note">{$t("settings.hotkeyFnHint")}</small>
              {/if}
            </div>
          </label>

          <label class="range-row">
            <span>{$t("settings.holdDuration")}</span>
            <div class="range-control">
              <input
                type="range"
                min="0.3"
                max="2"
                step="0.1"
                bind:value={localConfig.core.asr.hotkey_hold_time}
              />
              <output>
                {$t("settings.seconds", {
                  value: Number(localConfig.core.asr.hotkey_hold_time).toFixed(1),
                })}
              </output>
            </div>
          </label>

          <label>
            <span>
              {$t("settings.microphone")}
              <small>{$t("settings.microphoneHint")}</small>
            </span>
            <div class="device-control">
              <select bind:value={localConfig.core.asr.audio_device}>
                <option value="">{$t("settings.microphoneDefault")}</option>
                {#each audioDevices as device}
                  <option value={device.index}>{device.name}</option>
                {/each}
              </select>
              <button type="button" class="refresh-button" on:click={refreshAudioDevices}>
                {$t("settings.refreshDevices")}
              </button>
            </div>
          </label>
        </div>
      </section>

      <section>
        <h2>{$t("settings.group.engine")}</h2>
        <div class="panel service-panel">
          <label>
            <span>{$t("settings.engine")}</span>
            <select bind:value={localConfig.engine.current}>
              {#each engineOptions as engine}
                <option value={engine}>
                  {$t(engine === "volc_bigmodel" ? "engine.volcengine" : "engine.openai")}
                </option>
              {/each}
            </select>
          </label>

          <label>
            <span>{$t("settings.apiKey")}</span>
            {#if localConfig.engine.current === "volc_bigmodel"}
              <div class="secret-control">
                <input
                  type={showRecognitionApiKey ? "text" : "password"}
                  bind:value={localConfig.engine.volc_bigmodel.api_key}
                  placeholder={$t("settings.apiKeyPlaceholder")}
                />
                <button
                  type="button"
                  class="eye-button"
                  aria-label={showRecognitionApiKey ? $t("settings.hideApiKey") : $t("settings.showApiKey")}
                  on:click={() => (showRecognitionApiKey = !showRecognitionApiKey)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z" />
                    <circle cx="12" cy="12" r="2.5" />
                  </svg>
                </button>
              </div>
            {:else}
              <div class="secret-control">
                <input
                  type={showRecognitionApiKey ? "text" : "password"}
                  bind:value={localConfig.engine.openai.api_key}
                  placeholder={$t("settings.openaiApiKeyPlaceholder")}
                />
                <button
                  type="button"
                  class="eye-button"
                  aria-label={showRecognitionApiKey ? $t("settings.hideApiKey") : $t("settings.showApiKey")}
                  on:click={() => (showRecognitionApiKey = !showRecognitionApiKey)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z" />
                    <circle cx="12" cy="12" r="2.5" />
                  </svg>
                </button>
              </div>
            {/if}
          </label>
          <p class="hint">{$t("settings.apiKeyHint")}</p>
        </div>
      </section>

      <section>
        <h2>{$t("settings.group.language")}</h2>
        <div class="panel">
          <label>
            <span>{$t("settings.interfaceLanguage")}</span>
            <select
              value={localConfig.appearance.ui_language}
              on:change={(event) =>
                selectUiLanguage((event.target as HTMLSelectElement).value)}
            >
              {#each supportedLocales as code}
                <option value={code}>{$t(`language.${code}`)}</option>
              {/each}
            </select>
          </label>
        </div>
      </section>

      <section>
        <h2>{$t("settings.group.features")}</h2>
        <div class="panel feature-panel">
          <label>
            <span>
              {$t("settings.aiPolish")}
              <small>{$t("settings.aiPolishHint")}</small>
            </span>
            <input class="toggle" type="checkbox" bind:checked={localConfig.core.asr.llm_polish} />
          </label>
          {#if localConfig.core.asr.llm_polish}
            <label>
              <span>
                {$t("settings.polishBaseUrl")}
                <small>{$t("settings.polishBaseUrlHint")}</small>
              </span>
              <input
                type="text"
                bind:value={localConfig.llm.openai.base_url}
                placeholder={$t("settings.polishBaseUrlPlaceholder")}
              />
            </label>
            <label>
              <span>
                {$t("settings.polishApiKey")}
                <small>{$t("settings.polishApiKeyHint")}</small>
              </span>
              <div class="secret-control">
                <input
                  type={showPolishApiKey ? "text" : "password"}
                  bind:value={localConfig.llm.openai.api_key}
                  placeholder={$t("settings.polishApiKeyPlaceholder")}
                />
                <button
                  type="button"
                  class="eye-button"
                  aria-label={showPolishApiKey ? $t("settings.hideApiKey") : $t("settings.showApiKey")}
                  on:click={() => (showPolishApiKey = !showPolishApiKey)}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z" />
                    <circle cx="12" cy="12" r="2.5" />
                  </svg>
                </button>
              </div>
            </label>
            <label>
              <span>
                {$t("settings.polishModel")}
                <small>{$t("settings.polishModelHint")}</small>
              </span>
              <select bind:value={localConfig.llm.openai.model}>
                {#if !polishModelOptions.includes(localConfig.llm.openai.model)}
                  <option value={localConfig.llm.openai.model}>{localConfig.llm.openai.model}</option>
                {/if}
                {#each polishModelOptions as model}
                  <option value={model}>{model}</option>
                {/each}
              </select>
            </label>
          {/if}
          <label>
            <span>
              {$t("settings.soundNotification")}
              <small>{$t("settings.soundNotificationHint")}</small>
            </span>
            <input class="toggle" type="checkbox" bind:checked={localConfig.core.asr.sound_notification} />
          </label>
          <label>
            <span>
              {$t("settings.autoStart")}
              <small>{$t("settings.autoStartHint")}</small>
            </span>
            <input class="toggle" type="checkbox" bind:checked={localConfig.desktop.auto_start} />
          </label>
        </div>
      </section>
    {:else if activeTab === "history"}
      <HistoryPanel />
    {:else}
      <DiagnosticsDialog embedded={true} />
    {/if}
  </main>

  <footer>
    {#if validationError}<span class="validation-error">{validationError}</span>{/if}
    <button class="secondary" on:click={handleCancel}>
      {$t("settings.cancel")}
    </button>
    <button class="primary" on:click={handleSave} disabled={saving || !settingsLoaded}>
      {saving ? $t("settings.saving") : $t("settings.save")}
    </button>
  </footer>
</div>

<style>
  :global(html, body, #app) {
    width: 100%;
    height: 100%;
    margin: 0;
  }

  :global(*) {
    box-sizing: border-box;
  }

  .settings-dialog {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    background: #fafbfc;
    color: #20242a;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  header {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
    padding: 20px 30px 14px;
    background: #ffffff;
    border-bottom: 1px solid #e5e7eb;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  h1 {
    margin: 0;
    font-size: 21px;
    line-height: 1.3;
    font-weight: 720;
  }

  header img {
    width: 38px;
    height: 38px;
    flex: 0 0 auto;
  }

  header p {
    margin: 3px 0 0;
    color: #9ca3af;
    font-size: 12px;
  }

  nav {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
    padding: 4px;
    background: #ffffff;
    border: 1px solid #dfe3e8;
    border-radius: 13px;
  }

  nav button {
    min-width: 0;
    padding: 9px 14px;
    color: #969ba4;
    background: transparent;
    border: 0;
    border-radius: 9px;
    font-size: 13px;
    font-weight: 600;
  }

  nav button:hover {
    color: #1686f7;
    background: #f2f7fd;
  }

  nav button.active {
    color: #ffffff;
    background: #1686f7;
    box-shadow: 0 2px 7px rgba(22, 134, 247, 0.22);
  }

  main {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 22px 30px;
  }

  main.tool-page {
    padding-top: 25px;
  }

  section + section {
    margin-top: 17px;
  }

  h2 {
    margin: 0 0 8px 2px;
    color: #24282f;
    font-size: 14px;
    line-height: 1.4;
    font-weight: 700;
  }

  .panel {
    overflow: hidden;
    background: #ffffff;
    border: 1px solid #e1e5ea;
    border-radius: 14px;
  }

  label {
    display: flex;
    min-height: 50px;
    padding: 0 16px;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
  }

  label + label {
    border-top: 1px solid #eef0f3;
  }

  label > span {
    flex: 0 0 auto;
    color: #303640;
    font-size: 13px;
    font-weight: 550;
  }

  .hotkey-row {
    min-height: 116px;
    padding-top: 12px;
    padding-bottom: 12px;
    align-items: flex-start;
  }

  .hotkey-row > span {
    display: flex;
    padding-top: 8px;
    flex-direction: column;
    gap: 4px;
  }

  .hotkey-row > span small,
  .fn-note,
  .capture-message {
    color: #959ba5;
    font-size: 11px;
    font-weight: 400;
  }

  .hotkey-control {
    display: flex;
    width: 270px;
    min-width: 0;
    flex-direction: column;
    align-items: stretch;
    gap: 7px;
  }

  .hotkey-recorder {
    display: flex;
    width: 100%;
    min-width: 0;
    padding: 8px 10px;
    align-items: center;
    justify-content: space-between;
    color: #2563eb;
    background: #f8fbff;
    border-color: #bdd9fb;
  }

  .hotkey-recorder:hover,
  .hotkey-recorder.capturing {
    background: #eef6ff;
    border-color: #1686f7;
    box-shadow: 0 0 0 3px rgba(22, 134, 247, 0.1);
  }

  .hotkey-recorder kbd {
    padding: 3px 8px;
    color: #1f2937;
    background: #ffffff;
    border: 1px solid #d7dce2;
    border-bottom-width: 2px;
    border-radius: 6px;
    font-family: inherit;
    font-size: 12px;
    font-weight: 650;
  }

  .hotkey-recorder em {
    color: #1686f7;
    font-size: 11px;
    font-style: normal;
    font-weight: 600;
  }

  .quick-hotkeys {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }

  .quick-hotkeys button {
    min-width: 0;
    padding: 4px 7px;
    color: #68707c;
    background: #f7f8fa;
    border-color: #e0e4e9;
    border-radius: 6px;
    font-size: 10px;
    font-weight: 600;
  }

  .quick-hotkeys button:hover,
  .quick-hotkeys button.active {
    color: #1686f7;
    background: #eef6ff;
    border-color: #bcdcff;
  }

  .capture-message {
    color: #dc2626;
  }

  select,
  input[type="text"],
  input[type="password"] {
    width: 270px;
    min-width: 0;
    padding: 8px 10px;
    color: #111827;
    background: #f9fafb;
    border: 1px solid #d7dce2;
    border-radius: 8px;
    outline: none;
    font: inherit;
    font-size: 12px;
  }

  select:focus,
  input[type="text"]:focus,
  input[type="password"]:focus {
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
  }

  .device-control {
    display: flex;
    width: 270px;
    align-items: center;
    gap: 6px;
  }

  .device-control select {
    flex: 1;
    width: auto;
  }

  .refresh-button {
    flex: 0 0 auto;
    padding: 7px 8px;
    color: #526071;
    background: #f3f5f8;
    border: 1px solid #d7dce2;
    border-radius: 7px;
    font-size: 11px;
    white-space: nowrap;
  }

  .refresh-button:hover {
    color: #1686f7;
    border-color: #bcdcff;
    background: #eef6ff;
  }

  .secret-control {
    position: relative;
    display: flex;
    width: 270px;
    min-width: 0;
    align-items: center;
  }

  .secret-control input {
    width: 100%;
    padding-right: 38px;
  }

  .eye-button {
    position: absolute;
    right: 3px;
    display: inline-flex;
    width: 30px;
    min-width: 30px;
    height: 30px;
    padding: 0;
    align-items: center;
    justify-content: center;
    color: #7b8490;
    background: transparent;
    border: 0;
    border-radius: 6px;
  }

  .eye-button:hover {
    color: #1686f7;
    background: #eef6ff;
  }

  .eye-button svg {
    width: 17px;
    height: 17px;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .service-panel label {
    padding-top: 5px;
    padding-bottom: 5px;
  }

  .range-control {
    display: flex;
    width: 270px;
    align-items: center;
    gap: 10px;
  }

  .range-control input {
    flex: 1;
    min-width: 0;
    accent-color: #2563eb;
  }

  .range-control output {
    min-width: 50px;
    color: #6b7280;
    font-size: 12px;
    text-align: right;
  }

  .hint {
    margin: -2px 16px 10px;
    color: #9ca3af;
    font-size: 11px;
    text-align: right;
  }

  .feature-panel label {
    min-height: 62px;
  }

  .feature-panel label > span {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .feature-panel small {
    color: #959ba5;
    font-size: 11px;
    font-weight: 400;
  }

  input.toggle {
    position: relative;
    width: 42px;
    height: 24px;
    flex: 0 0 auto;
    margin: 0;
    appearance: none;
    border-radius: 999px;
    background: #d7dce2;
    cursor: pointer;
    transition: background 160ms ease;
  }

  input.toggle::after {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 18px;
    height: 18px;
    content: "";
    border-radius: 50%;
    background: #ffffff;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
    transition: transform 160ms ease;
  }

  input.toggle:checked {
    background: #14b889;
  }

  input.toggle:checked::after {
    transform: translateX(18px);
  }

  footer {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 12px 30px;
    background: #ffffff;
    border-top: 1px solid #e5e7eb;
  }

  .validation-error {
    margin-right: auto;
    align-self: center;
    color: #dc2626;
    font-size: 12px;
  }

  button {
    min-width: 72px;
    padding: 9px 16px;
    border-radius: 9px;
    border: 1px solid transparent;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }

  button.secondary {
    color: #4b5563;
    background: #ffffff;
    border-color: #d1d5db;
  }

  button.primary {
    color: #ffffff;
    background: #1686f7;
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }
</style>
