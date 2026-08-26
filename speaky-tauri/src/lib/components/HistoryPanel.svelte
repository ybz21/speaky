<script lang="ts">
  import { onMount } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { locale, t } from "../stores/i18n";

  interface HistoryItem {
    text: string;
    timestamp: number;
    engine: string;
    polished: boolean;
  }

  let items: HistoryItem[] = [];
  let copiedIndex: number | null = null;

  async function refresh() {
    items = await invoke<HistoryItem[]>("get_history");
  }

  async function copy(item: HistoryItem, index: number) {
    await invoke("copy_text", { text: item.text });
    copiedIndex = index;
    setTimeout(() => copiedIndex = null, 1400);
  }

  async function clear() {
    await invoke("clear_history");
    await refresh();
  }

  function formatTime(timestamp: number): string {
    return new Intl.DateTimeFormat($locale, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(timestamp * 1000));
  }

  onMount(refresh);
</script>

<div class="history-page">
  <div class="page-heading">
    <div>
      <h2>{$t("history.title")}</h2>
      <p>{$t("history.subtitle")}</p>
    </div>
    {#if items.length > 0}
      <button class="clear" on:click={clear}>{$t("history.clear")}</button>
    {/if}
  </div>

  {#if items.length === 0}
    <div class="empty">
      <div class="empty-icon">⌁</div>
      <h3>{$t("history.empty")}</h3>
      <p>{$t("history.emptyHint")}</p>
    </div>
  {:else}
    <div class="history-list">
      {#each items as item, index}
        <article>
          <div class="meta">
            <span>{formatTime(item.timestamp)}</span>
            {#if item.engine}<span>{item.engine}</span>{/if}
            {#if item.polished}<em>{$t("history.polished")}</em>{/if}
          </div>
          <p>{item.text}</p>
          <button on:click={() => copy(item, index)}>
            {copiedIndex === index ? $t("history.copied") : $t("history.copy")}
          </button>
        </article>
      {/each}
    </div>
  {/if}
</div>

<style>
  .history-page { min-height: 100%; }
  .page-heading { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 22px; }
  h2 { margin: 0; color: #15171a; font-size: 20px; font-weight: 700; }
  .page-heading p { margin: 7px 0 0; color: #8b9099; font-size: 13px; }
  button { border: 1px solid #dfe3e8; border-radius: 9px; background: #fff; color: #4c5563; cursor: pointer; font-size: 12px; }
  button:hover { border-color: #1686f7; color: #1686f7; }
  .clear { padding: 8px 14px; }
  .empty { display: flex; min-height: 360px; align-items: center; justify-content: center; flex-direction: column; border: 1px solid #e4e7eb; border-radius: 16px; background: #fff; }
  .empty-icon { display: grid; width: 54px; height: 54px; place-items: center; border-radius: 15px; background: #eef6ff; color: #1686f7; font-size: 30px; }
  .empty h3 { margin: 15px 0 5px; font-size: 15px; }
  .empty p { margin: 0; color: #9297a1; font-size: 12px; }
  .history-list { display: grid; gap: 10px; }
  article { position: relative; padding: 15px 92px 15px 17px; border: 1px solid #e4e7eb; border-radius: 13px; background: #fff; }
  article > p { margin: 8px 0 0; color: #303640; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
  article > button { position: absolute; top: 50%; right: 15px; min-width: 62px; padding: 7px 10px; transform: translateY(-50%); }
  .meta { display: flex; align-items: center; gap: 9px; color: #9aa0a9; font-size: 11px; }
  .meta em { padding: 2px 6px; border-radius: 5px; background: #eef6ff; color: #1686f7; font-style: normal; }
</style>
