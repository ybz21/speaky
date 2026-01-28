<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  export let audioLevel: number = 0;
  export let mode: string = "idle";
  export let appIcon: string | null = null;
  export let animating: boolean = false;

  const MODE_COLORS: Record<string, string> = {
    recording: "#00D9FF",
    recognizing: "#FFB84D",
    done: "#00E676",
    error: "#FF5252",
    idle: "#666666",
  };

  let phase = 0;
  let currentLevel = 0;
  let animationFrame: number | null = null;

  $: color = MODE_COLORS[mode] || MODE_COLORS.idle;

  function animate() {
    // Smooth audio level transition
    currentLevel += (audioLevel - currentLevel) * 0.2;

    // Breathing animation
    phase += 0.1;
    if (phase > Math.PI * 2) phase -= Math.PI * 2;

    if (animating) {
      animationFrame = requestAnimationFrame(animate);
    }
  }

  $: if (animating && !animationFrame) {
    animate();
  } else if (!animating && animationFrame) {
    cancelAnimationFrame(animationFrame);
    animationFrame = null;
    currentLevel = 0;
  }

  onDestroy(() => {
    if (animationFrame) {
      cancelAnimationFrame(animationFrame);
    }
  });

  $: breath = 0.5 + 0.5 * Math.sin(phase * 0.8);
  $: glowAlpha = 60 + 40 * breath;
</script>

<div class="orb-container">
  <svg width="64" height="64" viewBox="0 0 64 64">
    <!-- Background circle -->
    <defs>
      <radialGradient id="bgGradient" cx="0.4" cy="0.4" r="0.7">
        <stop offset="0%" stop-color="rgb(70, 70, 75)" />
        <stop offset="100%" stop-color="rgb(40, 40, 45)" />
      </radialGradient>
      <clipPath id="iconClip">
        <circle cx="32" cy="32" r="16" />
      </clipPath>
    </defs>

    <!-- Main circle background -->
    <circle
      cx="32"
      cy="32"
      r="24"
      fill="url(#bgGradient)"
      stroke="rgba(255, 255, 255, 0.1)"
      stroke-width="1"
    />

    <!-- App icon or microphone -->
    {#if appIcon}
      <image
        href={appIcon}
        x="16"
        y="16"
        width="32"
        height="32"
        clip-path="url(#iconClip)"
      />
    {:else}
      <!-- Default microphone icon -->
      <g stroke="rgb(220, 220, 220)" stroke-width="2.5" fill="none">
        <rect x="27" y="22" width="10" height="14" rx="5" ry="5" />
        <path d="M 24 40 A 8 5 0 0 0 40 40" />
        <line x1="32" y1="45" x2="32" y2="50" />
      </g>
    {/if}

    <!-- Status indicator dot glow -->
    <circle
      cx="49"
      cy="49"
      r="9"
      fill={`rgba(${hexToRgb(color)}, ${glowAlpha / 255})`}
    />

    <!-- Status indicator dot -->
    <circle
      cx="49"
      cy="49"
      r="5"
      fill={color}
      stroke="rgb(40, 40, 45)"
      stroke-width="2"
    />
  </svg>
</div>

<script context="module" lang="ts">
  function hexToRgb(hex: string): string {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (result) {
      return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`;
    }
    return "102, 102, 102";
  }
</script>

<style>
  .orb-container {
    width: 64px;
    height: 64px;
  }
</style>
