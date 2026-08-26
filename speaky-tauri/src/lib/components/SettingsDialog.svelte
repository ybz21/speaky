<script lang="ts">
  import { onMount } from "svelte";
  import { config, type Config, defaultConfig } from "../stores/config";
  import {
    t,
    locale,
    normalizeLocale,
    supportedLocales,
  } from "../stores/i18n";
  import logoUrl from "../../../../resources/icon.svg?url";

  let localConfig: Config = JSON.parse(JSON.stringify(defaultConfig));
  let saving = false;

  const hotkeyOptions = ["ctrl", "alt", "shift", "cmd", "f8"];
  const engineOptions = ["volc_bigmodel", "openai"] as const;

  onMount(async () => {
    await config.load();
    localConfig = JSON.parse(JSON.stringify($config));
    localConfig.appearance.ui_language = normalizeLocale(
      localConfig.appearance.ui_language,
    );
    locale.setLocale(localConfig.appearance.ui_language);
  });

  function selectUiLanguage(value: string) {
    localConfig.appearance.ui_language = normalizeLocale(value);
    locale.setLocale(localConfig.appearance.ui_language);
  }

  async function handleSave() {
    saving = true;
    try {
      const normalizedConfig: Config = JSON.parse(JSON.stringify(localConfig));
      const selectedDevice = Number(normalizedConfig.core.asr.audio_device);
      normalizedConfig.core.asr.audio_device =
        normalizedConfig.core.asr.audio_device === null ||
        normalizedConfig.core.asr.audio_device === undefined ||
        Number.isNaN(selectedDevice)
          ? null
          : selectedDevice;

      // Recognition language is intentionally automatic and no longer exposed.
      normalizedConfig.core.asr.language = "auto";
      normalizedConfig.core.asr.streaming_mode = true;
      normalizedConfig.appearance.theme = "light";
      await config.save(normalizedConfig);

      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().hide();
    } catch (error) {
      console.error("Failed to save config:", error);
    } finally {
      saving = false;
    }
  }

  async function handleCancel() {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().hide();
  }
</script>

<div class="settings-dialog">
  <header>
    <img src={logoUrl} alt="" />
    <div>
      <h1>{$t("settings.title")}</h1>
      <p>{$t("settings.subtitle")}</p>
    </div>
  </header>

  <main>
    <section>
      <h2>{$t("settings.group.trigger")}</h2>
      <div class="panel">
        <label>
          <span>{$t("settings.hotkey")}</span>
          <select bind:value={localConfig.core.asr.hotkey}>
            {#each hotkeyOptions as hotkey}
              <option value={hotkey}>{hotkey.toUpperCase()}</option>
            {/each}
          </select>
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
            <input
              type="password"
              bind:value={localConfig.engine.volc_bigmodel.api_key}
              placeholder={$t("settings.apiKeyPlaceholder")}
            />
          {:else}
            <input
              type="password"
              bind:value={localConfig.engine.openai.api_key}
              placeholder={$t("settings.openaiApiKeyPlaceholder")}
            />
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
  </main>

  <footer>
    <button class="secondary" on:click={handleCancel}>
      {$t("settings.cancel")}
    </button>
    <button class="primary" on:click={handleSave} disabled={saving}>
      {saving ? $t("settings.saving") : $t("settings.save")}
    </button>
  </footer>
</div>

<style>
  .settings-dialog {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    background: #f7f8fa;
    color: #1f2937;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 20px 12px;
    background: #ffffff;
    border-bottom: 1px solid #e5e7eb;
  }

  h1 {
    margin: 0;
    font-size: 18px;
    line-height: 1.3;
    font-weight: 650;
  }

  header img {
    width: 30px;
    height: 30px;
    flex: 0 0 auto;
  }

  header p {
    margin: 3px 0 0;
    color: #9ca3af;
    font-size: 12px;
  }

  main {
    flex: 1;
    overflow: hidden;
    padding: 10px 20px 6px;
  }

  section + section {
    margin-top: 10px;
  }

  h2 {
    margin: 0 0 6px 2px;
    color: #6b7280;
    font-size: 11px;
    line-height: 1.4;
    font-weight: 650;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .panel {
    overflow: hidden;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
  }

  label {
    display: flex;
    min-height: 40px;
    padding: 0 12px;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
  }

  label + label {
    border-top: 1px solid #eef0f3;
  }

  label > span {
    flex: 0 0 auto;
    color: #374151;
    font-size: 13px;
  }

  select,
  input[type="password"] {
    width: 190px;
    min-width: 0;
    padding: 7px 9px;
    color: #111827;
    background: #f9fafb;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    outline: none;
    font: inherit;
    font-size: 12px;
  }

  select:focus,
  input[type="password"]:focus {
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
  }

  .service-panel label {
    padding-top: 4px;
    padding-bottom: 4px;
  }

  .range-control {
    display: flex;
    width: 190px;
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
    margin: -1px 12px 8px;
    color: #9ca3af;
    font-size: 11px;
    text-align: right;
  }

  footer {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 10px 20px;
    background: #ffffff;
    border-top: 1px solid #e5e7eb;
  }

  button {
    min-width: 72px;
    padding: 8px 14px;
    border-radius: 7px;
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
    background: #2563eb;
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }
</style>
