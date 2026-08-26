<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { config } from "../stores/config";
  import { locale, t } from "../stores/i18n";

  export let embedded = false;

  interface Device {
    index: number;
    name: string;
    selected: boolean;
  }

  interface Snapshot {
    app_version: string;
    platform: string;
    microphone_ready: boolean;
    devices: Device[];
    permissions: { microphone: string; accessibility: string };
    engine: string;
    engine_ready: boolean;
    log_path: string;
  }

  let snapshot: Snapshot | null = null;
  let logs = "";
  let notice = "";
  let timer: ReturnType<typeof setInterval> | null = null;

  function permissionLabel(value: string): string {
    if (value === "granted") return $t("diagnostics.granted");
    if (value === "not_required") return $t("diagnostics.notRequired");
    if (value === "not_determined") return $t("diagnostics.notDetermined");
    return $t("diagnostics.denied");
  }

  async function refresh() {
    snapshot = await invoke<Snapshot>("get_diagnostics");
    logs = await invoke<string>("read_diagnostic_log");
  }

  async function copyLogs() {
    await invoke("copy_text", { text: logs });
    notice = $t("diagnostics.copied");
  }

  async function exportLogs() {
    const path = await invoke<string>("export_diagnostic_log");
    notice = $t("diagnostics.exported", { path });
  }

  async function clearLogs() {
    await invoke("clear_diagnostic_log");
    await refresh();
  }

  onMount(async () => {
    await config.load();
    let currentLocale = "zh-CN";
    const unsubscribe = config.subscribe((value) => {
      currentLocale = value.appearance.ui_language;
    });
    unsubscribe();
    locale.setLocale(currentLocale);
    await refresh();
    timer = setInterval(async () => {
      logs = await invoke<string>("read_diagnostic_log");
    }, 2000);
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
  });
</script>

<div class="dialog" class:embedded>
  {#if !embedded}
    <header>
      <div>
        <h1>{$t("diagnostics.title")}</h1>
        <p>{$t("diagnostics.subtitle")}</p>
      </div>
      {#if snapshot}<span>v{snapshot.app_version} · {snapshot.platform}</span>{/if}
    </header>
  {/if}

  <main class:embedded>
    {#if embedded}
      <div class="page-heading">
        <div>
          <h1>{$t("diagnostics.title")}</h1>
          <p>{$t("diagnostics.subtitle")}</p>
        </div>
        {#if snapshot}<span>v{snapshot.app_version} · {snapshot.platform}</span>{/if}
      </div>
    {/if}
    <div class="grid">
      <section>
        <h2>{$t("diagnostics.microphone")}</h2>
        <div class="status" class:ok={snapshot?.microphone_ready}>
          <i></i>
          {snapshot?.microphone_ready ? $t("diagnostics.ready") : $t("diagnostics.unavailable")}
        </div>
        <h3>{$t("diagnostics.devices")}</h3>
        <ul>
          {#each snapshot?.devices ?? [] as device}
            <li>{device.name}{#if device.selected}<em>{$t("diagnostics.selected")}</em>{/if}</li>
          {:else}
            <li class="muted">{$t("diagnostics.noDevices")}</li>
          {/each}
        </ul>
      </section>

      <section>
        <h2>{$t("diagnostics.permissions")}</h2>
        <dl>
          <div><dt>{$t("diagnostics.microphonePermission")}</dt><dd>{permissionLabel(snapshot?.permissions.microphone ?? "unknown")}</dd></div>
          <div><dt>{$t("diagnostics.accessibilityPermission")}</dt><dd>{permissionLabel(snapshot?.permissions.accessibility ?? "unknown")}</dd></div>
          <div><dt>{$t("diagnostics.engine")}</dt><dd>{snapshot?.engine ?? "—"} · {snapshot?.engine_ready ? $t("diagnostics.ready") : $t("diagnostics.unavailable")}</dd></div>
        </dl>
        {#if snapshot?.permissions.microphone === "denied" || snapshot?.permissions.microphone === "not_determined" || snapshot?.permissions.accessibility === "denied"}
          <button class="link" on:click={() => invoke("open_permission_settings")}>{$t("diagnostics.openPermissions")}</button>
        {/if}
      </section>
    </div>

    <section class="logs">
      <div class="section-title">
        <div><h2>{$t("diagnostics.logs")}</h2><small>{snapshot?.log_path}</small></div>
        <button on:click={refresh}>{$t("diagnostics.refresh")}</button>
      </div>
      <pre>{logs}</pre>
      <div class="actions">
        <span>{notice}</span>
        <button on:click={clearLogs}>{$t("diagnostics.clear")}</button>
        <button on:click={copyLogs}>{$t("diagnostics.copy")}</button>
        <button class="primary" on:click={exportLogs}>{$t("diagnostics.export")}</button>
      </div>
    </section>
  </main>

  {#if !embedded}
    <footer><button on:click={() => getCurrentWindow().hide()}>{$t("diagnostics.close")}</button></footer>
  {/if}
</div>

<style>
  :global(html, body, #app) { margin: 0; width: 100%; height: 100%; }
  :global(*) { box-sizing: border-box; }
  .dialog { width: 100%; height: 100%; display: flex; flex-direction: column; background: #f7f8fa; color: #1f2937; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .dialog.embedded { background: transparent; }
  header { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px; background: white; border-bottom: 1px solid #e5e7eb; }
  h1 { margin: 0; font-size: 19px; } header p { margin: 4px 0 0; color: #8b95a5; font-size: 12px; } header span { color: #9ca3af; font-size: 12px; }
  main { flex: 1; min-height: 0; padding: 16px 22px; overflow: auto; }
  main.embedded { padding: 0; overflow: visible; }
  .page-heading { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 22px; }
  .page-heading h1 { margin: 0; color: #15171a; font-size: 20px; font-weight: 700; }
  .page-heading p { margin: 7px 0 0; color: #8b9099; font-size: 13px; }
  .page-heading span { color: #9ca3af; font-size: 12px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  section { background: white; border: 1px solid #e4e7eb; border-radius: 14px; padding: 16px; }
  h2 { margin: 0; font-size: 14px; } h3 { margin: 13px 0 6px; color: #6b7280; font-size: 11px; font-weight: 600; }
  .status { display: flex; align-items: center; gap: 7px; margin-top: 11px; color: #dc2626; font-size: 13px; } .status.ok { color: #15803d; }
  .status i { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
  ul { max-height: 76px; margin: 0; padding: 0; overflow: auto; list-style: none; } li { display: flex; justify-content: space-between; padding: 3px 0; color: #4b5563; font-size: 12px; } li em { color: #2563eb; font-style: normal; } .muted { color: #9ca3af; }
  dl { margin: 10px 0 0; } dl div { display: flex; justify-content: space-between; gap: 12px; padding: 5px 0; font-size: 12px; } dt { color: #6b7280; } dd { margin: 0; text-align: right; }
  button { padding: 7px 11px; border: 1px solid #d1d5db; border-radius: 7px; background: white; color: #374151; cursor: pointer; font-size: 12px; } button:hover { background: #f3f4f6; } button.primary { border-color: #2563eb; background: #2563eb; color: white; } button.link { margin-top: 8px; border: 0; padding-left: 0; color: #2563eb; }
  .logs { margin-top: 12px; } .section-title { display: flex; align-items: center; justify-content: space-between; } small { display: block; max-width: 470px; margin-top: 3px; overflow: hidden; color: #9ca3af; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
  pre { height: 190px; margin: 10px 0; padding: 10px; overflow: auto; border-radius: 7px; background: #111827; color: #d1d5db; font: 10px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; }
  .actions { display: flex; justify-content: flex-end; align-items: center; gap: 7px; } .actions span { flex: 1; overflow: hidden; color: #15803d; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
  footer { display: flex; justify-content: flex-end; padding: 11px 22px; background: white; border-top: 1px solid #e5e7eb; }
</style>
