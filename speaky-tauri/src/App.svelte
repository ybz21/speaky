<script lang="ts">
  import FloatingWindow from "./lib/components/FloatingWindow.svelte";
  import SettingsDialog from "./lib/components/SettingsDialog.svelte";
  import { appState } from "./lib/stores/app";

  // Check which window we're in based on URL or label
  const isSettings = window.location.hash === "#settings";
</script>

{#if isSettings}
  <SettingsDialog />
{:else}
  <FloatingWindow />
{/if}
