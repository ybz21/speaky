<script lang="ts">
  import FloatingWindow from "./lib/components/FloatingWindow.svelte";
  import SettingsDialog from "./lib/components/SettingsDialog.svelte";
  import DiagnosticsDialog from "./lib/components/DiagnosticsDialog.svelte";
  import { appState } from "./lib/stores/app";

  // Check which window we're in based on URL or label
  const isSettings = window.location.hash === "#settings";
  const isDiagnostics = window.location.hash === "#diagnostics";
</script>

{#if isDiagnostics}
  <DiagnosticsDialog />
{:else if isSettings}
  <SettingsDialog />
{:else}
  <FloatingWindow />
{/if}
