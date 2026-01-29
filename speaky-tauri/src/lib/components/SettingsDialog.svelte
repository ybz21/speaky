<script lang="ts">
  import { onMount } from "svelte";
  import { config, type Config } from "../stores/config";
  import { t, locale, locales, type Locale } from "../stores/i18n";
  import { getAudioDevices } from "../utils/tauri";

  let currentTab = "core";
  let localConfig: Config;
  let audioDevices: Array<{ index: number; name: string }> = [];
  let saving = false;

  const tabs = [
    { id: "core", label: "tab_core" },
    { id: "engine", label: "tab_engine" },
    { id: "appearance", label: "tab_appearance" },
  ];

  // Hotkey options - now supports modifier keys with rdev
  const hotkeyOptions = [
    // Modifier keys (supported with rdev)
    "ctrl", "alt", "shift", "cmd",
    "ctrl_l", "ctrl_r", "alt_l", "alt_r", "shift_l", "shift_r",
    // Function keys
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    // Other keys
    "space", "tab", "capslock", "pause", "insert", "scrolllock", "backquote",
  ];

  const engineOptions = [
    { value: "volc_bigmodel", label: "火山引擎-语音大模型" },
    { value: "openai", label: "OpenAI Whisper" },
  ];

  const languageOptions = [
    { value: "zh", label: "中文" },
    { value: "en", label: "English" },
    { value: "ja", label: "日本語" },
    { value: "ko", label: "한국어" },
  ];

  const themeOptions = [
    { value: "auto", labelKey: "theme_auto" },
    { value: "light", labelKey: "theme_light" },
    { value: "dark", labelKey: "theme_dark" },
  ];

  config.subscribe((c) => {
    localConfig = JSON.parse(JSON.stringify(c));
  });

  onMount(async () => {
    await config.load();
    try {
      audioDevices = await getAudioDevices();
    } catch (e) {
      console.error("Failed to get audio devices:", e);
    }
  });

  async function handleSave() {
    saving = true;
    try {
      await config.save(localConfig);
      // Close window after saving
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().close();
    } catch (e) {
      console.error("Failed to save config:", e);
    } finally {
      saving = false;
    }
  }

  async function handleCancel() {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().close();
  }
</script>

<div class="settings-dialog">
  <div class="header">
    <h1>{$t("settings_title")}</h1>
  </div>

  <div class="tabs">
    {#each tabs as tab}
      <button
        class="tab"
        class:active={currentTab === tab.id}
        on:click={() => (currentTab = tab.id)}
      >
        {$t(tab.label)}
      </button>
    {/each}
  </div>

  <div class="content">
    {#if currentTab === "core"}
      <div class="group-label">{$t("voice_input_group")}</div>

      <div class="card">
        <span class="card-label">{$t("hotkey_label")}</span>
        <select bind:value={localConfig.core.asr.hotkey}>
          {#each hotkeyOptions as opt}
            <option value={opt}>{opt.toUpperCase()}</option>
          {/each}
        </select>
      </div>

      <div class="card">
        <span class="card-label">{$t("hold_time_label")}</span>
        <div class="range-group">
          <input
            type="range"
            min="0"
            max="3"
            step="0.1"
            bind:value={localConfig.core.asr.hotkey_hold_time}
          />
          <span class="range-value">{localConfig.core.asr.hotkey_hold_time.toFixed(1)}{$t("seconds")}</span>
        </div>
      </div>

      <div class="card">
        <span class="card-label">{$t("recognition_lang")}</span>
        <select bind:value={localConfig.core.asr.language}>
          {#each languageOptions as opt}
            <option value={opt.value}>{opt.label}</option>
          {/each}
        </select>
      </div>

      <div class="card">
        <span class="card-label">{$t("audio_device")}</span>
        <select bind:value={localConfig.core.asr.audio_device}>
          <option value={null}>{$t("audio_device_default")}</option>
          {#each audioDevices as device}
            <option value={device.index}>{device.name}</option>
          {/each}
        </select>
      </div>

      <div class="card">
        <span class="card-label">{$t("audio_gain")}</span>
        <div class="range-group">
          <input
            type="range"
            min="0.5"
            max="3"
            step="0.1"
            bind:value={localConfig.core.asr.audio_gain}
          />
          <span class="range-value">{localConfig.core.asr.audio_gain.toFixed(1)}x</span>
        </div>
      </div>

      <div class="card">
        <span class="card-label">{$t("streaming_mode")}</span>
        <label class="switch">
          <input type="checkbox" bind:checked={localConfig.core.asr.streaming_mode} />
          <span class="slider"></span>
        </label>
      </div>
    {/if}

    {#if currentTab === "engine"}
      <div class="group-label">{$t("engine_group")}</div>

      <div class="card">
        <span class="card-label">{$t("engine_label")}</span>
        <select bind:value={localConfig.engine.current}>
          {#each engineOptions as opt}
            <option value={opt.value}>{opt.label}</option>
          {/each}
        </select>
      </div>

      {#if localConfig.engine.current === "volc_bigmodel"}
        <div class="group-label">{$t("volc_bigmodel_settings")}</div>

        <div class="card vertical">
          <span class="card-label">{$t("app_key")}</span>
          <input
            type="password"
            bind:value={localConfig.engine.volc_bigmodel.app_key}
            placeholder="Enter app key"
          />
        </div>

        <div class="card vertical">
          <span class="card-label">{$t("access_key")}</span>
          <input
            type="password"
            bind:value={localConfig.engine.volc_bigmodel.access_key}
            placeholder="Enter access key"
          />
        </div>
      {/if}

      {#if localConfig.engine.current === "openai"}
        <div class="group-label">{$t("openai_settings")}</div>

        <div class="card vertical">
          <span class="card-label">{$t("api_key")}</span>
          <input
            type="password"
            bind:value={localConfig.engine.openai.api_key}
            placeholder="sk-..."
          />
        </div>

        <div class="card vertical">
          <span class="card-label">{$t("model")}</span>
          <select bind:value={localConfig.engine.openai.model}>
            <option value="gpt-4o-transcribe">gpt-4o-transcribe</option>
            <option value="gpt-4o-mini-transcribe">gpt-4o-mini-transcribe</option>
            <option value="whisper-1">whisper-1</option>
          </select>
        </div>

        <div class="card vertical">
          <span class="card-label">{$t("base_url")}</span>
          <input
            type="text"
            bind:value={localConfig.engine.openai.base_url}
            placeholder="https://api.openai.com/v1"
          />
        </div>
      {/if}
    {/if}

    {#if currentTab === "appearance"}
      <div class="group-label">{$t("ui_group")}</div>

      <div class="card">
        <span class="card-label">{$t("theme")}</span>
        <select bind:value={localConfig.appearance.theme}>
          {#each themeOptions as opt}
            <option value={opt.value}>{$t(opt.labelKey)}</option>
          {/each}
        </select>
      </div>

      <div class="card">
        <span class="card-label">{$t("ui_lang")}</span>
        <select
          value={localConfig.appearance.ui_language}
          on:change={(e) => {
            const target = e.target as HTMLSelectElement;
            localConfig.appearance.ui_language = target.value;
            locale.setLocale(target.value as Locale | "auto");
          }}
        >
          <option value="auto">{$t("auto")}</option>
          {#each locales as loc}
            <option value={loc}>{loc}</option>
          {/each}
        </select>
      </div>

      <div class="card">
        <span class="card-label">{$t("window_opacity")}</span>
        <div class="range-group">
          <input
            type="range"
            min="0.5"
            max="1"
            step="0.05"
            bind:value={localConfig.appearance.window_opacity}
          />
          <span class="range-value">{Math.round(localConfig.appearance.window_opacity * 100)}%</span>
        </div>
      </div>

      <div class="card">
        <span class="card-label">{$t("show_waveform")}</span>
        <label class="switch">
          <input type="checkbox" bind:checked={localConfig.appearance.show_waveform} />
          <span class="slider"></span>
        </label>
      </div>
    {/if}
  </div>

  <div class="footer">
    <button class="btn secondary" on:click={handleCancel}>
      {$t("cancel")}
    </button>
    <button class="btn primary" on:click={handleSave} disabled={saving}>
      {saving ? "..." : $t("save")}
    </button>
  </div>
</div>

<style>
  .settings-dialog {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    color: #f6f6f6;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  .header {
    padding: 20px 24px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .header h1 {
    font-size: 20px;
    font-weight: 600;
    margin: 0;
  }

  .tabs {
    display: flex;
    gap: 4px;
    padding: 12px 24px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .tab {
    padding: 8px 16px;
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.6);
    cursor: pointer;
    border-radius: 6px;
    font-size: 14px;
    transition: all 0.2s;
  }

  .tab:hover {
    background: rgba(255, 255, 255, 0.05);
    color: rgba(255, 255, 255, 0.8);
  }

  .tab.active {
    background: rgba(0, 217, 255, 0.15);
    color: #00d9ff;
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 20px 24px;
  }

  .group-label {
    font-size: 13px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.5);
    margin: 16px 0 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .group-label:first-child {
    margin-top: 0;
  }

  /* Card style - matches Python qfluentwidgets SettingCard */
  .card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    padding: 0 20px;
    margin-bottom: 8px;
    background: rgba(255, 255, 255, 0.04);
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.06);
  }

  .card.vertical {
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    height: auto;
    padding: 16px 20px;
    gap: 8px;
  }

  .card.vertical input,
  .card.vertical select {
    width: 100%;
  }

  .card-label {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.9);
  }

  .card select,
  .card input[type="text"],
  .card input[type="password"] {
    min-width: 150px;
    padding: 8px 12px;
    background: rgba(30, 30, 40, 0.9);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    color: #f6f6f6;
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
  }

  .card select:focus,
  .card input:focus {
    border-color: #00d9ff;
  }

  .card select {
    cursor: pointer;
    /* Fix dropdown options styling */
    color-scheme: dark;
  }

  .card select option {
    background: #1a1a2e;
    color: #f6f6f6;
    padding: 8px;
  }

  /* Range input group */
  .range-group {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 180px;
  }

  .range-group input[type="range"] {
    flex: 1;
    height: 4px;
    accent-color: #00d9ff;
    cursor: pointer;
  }

  .range-value {
    min-width: 50px;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.7);
    text-align: right;
  }

  /* Toggle switch */
  .switch {
    position: relative;
    display: inline-block;
    width: 44px;
    height: 24px;
  }

  .switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .slider {
    position: absolute;
    cursor: pointer;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(255, 255, 255, 0.15);
    transition: 0.3s;
    border-radius: 24px;
  }

  .slider:before {
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: 0.3s;
    border-radius: 50%;
  }

  .switch input:checked + .slider {
    background-color: #00d9ff;
  }

  .switch input:checked + .slider:before {
    transform: translateX(20px);
  }

  .footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    padding: 16px 24px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }

  .btn {
    padding: 10px 24px;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn.primary {
    background: #00d9ff;
    color: #1a1a2e;
  }

  .btn.primary:hover {
    background: #00c4e6;
  }

  .btn.primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn.secondary {
    background: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.8);
  }

  .btn.secondary:hover {
    background: rgba(255, 255, 255, 0.12);
  }
</style>
