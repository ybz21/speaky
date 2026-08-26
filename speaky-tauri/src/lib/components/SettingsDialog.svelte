<script lang="ts">
  import { onMount, tick } from "svelte";
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
  import logoUrl from "../../../../resources/icon.svg?url";

  let localConfig: Config = JSON.parse(JSON.stringify(defaultConfig));
  let saving = false;
  let activeTab: "general" | "history" | "diagnostics" = "general";
  let contentElement: HTMLElement;

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

  async function selectTab(tab: "general" | "history" | "diagnostics") {
    activeTab = tab;
    await tick();
    contentElement?.scrollTo({ top: 0 });
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

      await getCurrentWindow().hide();
    } catch (error) {
      console.error("Failed to save config:", error);
    } finally {
      saving = false;
    }
  }

  async function handleCancel() {
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
                {$t("settings.polishApiKey")}
                <small>{$t("settings.polishApiKeyHint")}</small>
              </span>
              <input
                type="password"
                bind:value={localConfig.llm.openai.api_key}
                placeholder={$t("settings.polishApiKeyPlaceholder")}
              />
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
    <button class="secondary" on:click={handleCancel}>
      {$t("settings.cancel")}
    </button>
    <button class="primary" on:click={handleSave} disabled={saving}>
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

  select,
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
  input[type="password"]:focus {
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
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
