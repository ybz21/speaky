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

  const hotkeyOptions = [
    "ctrl",
    "alt",
    "shift",
    "cmd",
    "f1",
    "f2",
    "f3",
    "f4",
    "f5",
    "f6",
    "f7",
    "f8",
    "f9",
    "f10",
    "f11",
    "f12",
    "space",
    "tab",
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
      <div class="section">
        <h3>{$t("hotkey_label")}</h3>
        <select bind:value={localConfig.core.asr.hotkey}>
          {#each hotkeyOptions as opt}
            <option value={opt}>{opt.toUpperCase()}</option>
          {/each}
        </select>
      </div>

      <div class="section">
        <h3>{$t("hold_time_label")}</h3>
        <div class="range-input">
          <input
            type="range"
            min="0"
            max="3"
            step="0.1"
            bind:value={localConfig.core.asr.hotkey_hold_time}
          />
          <span>{localConfig.core.asr.hotkey_hold_time}{$t("seconds")}</span>
        </div>
      </div>

      <div class="section">
        <h3>{$t("recognition_lang")}</h3>
        <select bind:value={localConfig.core.asr.language}>
          {#each languageOptions as opt}
            <option value={opt.value}>{opt.label}</option>
          {/each}
        </select>
      </div>

      <div class="section">
        <h3>{$t("audio_device")}</h3>
        <select bind:value={localConfig.core.asr.audio_device}>
          <option value={null}>{$t("audio_device_default")}</option>
          {#each audioDevices as device}
            <option value={device.index}>{device.name}</option>
          {/each}
        </select>
      </div>

      <div class="section">
        <h3>{$t("audio_gain")}</h3>
        <div class="range-input">
          <input
            type="range"
            min="0.5"
            max="3"
            step="0.1"
            bind:value={localConfig.core.asr.audio_gain}
          />
          <span>{localConfig.core.asr.audio_gain.toFixed(1)}x</span>
        </div>
      </div>

      <div class="section checkbox">
        <label>
          <input
            type="checkbox"
            bind:checked={localConfig.core.asr.streaming_mode}
          />
          {$t("streaming_mode")}
        </label>
      </div>
    {/if}

    {#if currentTab === "engine"}
      <div class="section">
        <h3>{$t("engine_label")}</h3>
        <select bind:value={localConfig.engine.current}>
          {#each engineOptions as opt}
            <option value={opt.value}>{opt.label}</option>
          {/each}
        </select>
      </div>

      {#if localConfig.engine.current === "volc_bigmodel"}
        <div class="section">
          <h3>{$t("app_key")}</h3>
          <input
            type="password"
            bind:value={localConfig.engine.volc_bigmodel.app_key}
            placeholder="Enter app key"
          />
        </div>
        <div class="section">
          <h3>{$t("access_key")}</h3>
          <input
            type="password"
            bind:value={localConfig.engine.volc_bigmodel.access_key}
            placeholder="Enter access key"
          />
        </div>
      {/if}

      {#if localConfig.engine.current === "openai"}
        <div class="section">
          <h3>{$t("api_key")}</h3>
          <input
            type="password"
            bind:value={localConfig.engine.openai.api_key}
            placeholder="sk-..."
          />
        </div>
        <div class="section">
          <h3>{$t("base_url")}</h3>
          <input
            type="text"
            bind:value={localConfig.engine.openai.base_url}
            placeholder="https://api.openai.com/v1"
          />
        </div>
      {/if}
    {/if}

    {#if currentTab === "appearance"}
      <div class="section">
        <h3>{$t("theme")}</h3>
        <select bind:value={localConfig.appearance.theme}>
          {#each themeOptions as opt}
            <option value={opt.value}>{$t(opt.labelKey)}</option>
          {/each}
        </select>
      </div>

      <div class="section">
        <h3>{$t("ui_lang")}</h3>
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

      <div class="section">
        <h3>{$t("window_opacity")}</h3>
        <div class="range-input">
          <input
            type="range"
            min="0.5"
            max="1"
            step="0.05"
            bind:value={localConfig.appearance.window_opacity}
          />
          <span>{Math.round(localConfig.appearance.window_opacity * 100)}%</span>
        </div>
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
  }

  .header {
    padding: 16px 24px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }

  .header h1 {
    font-size: 18px;
    font-weight: 600;
    margin: 0;
  }

  .tabs {
    display: flex;
    gap: 4px;
    padding: 8px 24px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
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
    padding: 24px;
  }

  .section {
    margin-bottom: 20px;
  }

  .section h3 {
    font-size: 13px;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.7);
    margin-bottom: 8px;
  }

  .section select,
  .section input[type="text"],
  .section input[type="password"] {
    width: 100%;
    padding: 10px 12px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    color: #f6f6f6;
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
  }

  .section select:focus,
  .section input:focus {
    border-color: #00d9ff;
  }

  .section.checkbox label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }

  .section.checkbox input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: #00d9ff;
  }

  .range-input {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .range-input input[type="range"] {
    flex: 1;
    height: 4px;
    accent-color: #00d9ff;
  }

  .range-input span {
    min-width: 60px;
    text-align: right;
    font-size: 14px;
    color: rgba(255, 255, 255, 0.8);
  }

  .footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    padding: 16px 24px;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
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
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.8);
  }

  .btn.secondary:hover {
    background: rgba(255, 255, 255, 0.15);
  }
</style>
