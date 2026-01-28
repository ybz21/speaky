<script lang="ts">
  import { onDestroy } from "svelte";

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
  let currentColor = { r: 0, g: 217, b: 255 }; // Default to recording color
  let animationFrame: number | null = null;

  // Computed values that get updated in animation loop
  let breath = 0.5;
  let glowAlpha = 0.3;

  $: targetColor = hexToRgbObj(MODE_COLORS[mode] || MODE_COLORS.idle);

  function hexToRgbObj(hex: string): { r: number; g: number; b: number } {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (result) {
      return {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      };
    }
    return { r: 102, g: 102, b: 102 };
  }

  function lerpColor(
    c1: { r: number; g: number; b: number },
    c2: { r: number; g: number; b: number },
    t: number
  ) {
    return {
      r: Math.round(c1.r + (c2.r - c1.r) * t),
      g: Math.round(c1.g + (c2.g - c1.g) * t),
      b: Math.round(c1.b + (c2.b - c1.b) * t),
    };
  }

  function animate() {
    // Smooth audio level transition (EMA filter)
    currentLevel = currentLevel + (audioLevel - currentLevel) * 0.2;

    // Smooth color transition - reassign to trigger reactivity
    currentColor = lerpColor(currentColor, targetColor, 0.15);

    // Breathing animation phase
    phase = phase + 0.1;
    if (phase > Math.PI * 2) phase = phase - Math.PI * 2;

    // Update computed values (reassign to trigger Svelte reactivity)
    breath = 0.5 + 0.5 * Math.sin(phase * 0.8);
    glowAlpha = (60 + 40 * breath) / 255;

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
</script>

<div class="orb-container">
  <svg width="64" height="64" viewBox="0 0 64 64">
    <defs>
      <!-- Background gradient (radial, offset to top-left) -->
      <radialGradient id="bgGradient" cx="0.4" cy="0.4" r="0.75">
        <stop offset="0%" stop-color="rgba(70, 70, 75, 0.98)" />
        <stop offset="100%" stop-color="rgba(40, 40, 45, 0.98)" />
      </radialGradient>

      <!-- Icon clip path -->
      <clipPath id="iconClip">
        <circle cx="32" cy="32" r="16" />
      </clipPath>

      <!-- Glow gradient for status dot -->
      <radialGradient id="glowGradient" cx="0.5" cy="0.5" r="0.5">
        <stop
          offset="0%"
          stop-color="rgba({currentColor.r}, {currentColor.g}, {currentColor.b}, {glowAlpha})"
        />
        <stop
          offset="100%"
          stop-color="rgba({currentColor.r}, {currentColor.g}, {currentColor.b}, 0)"
        />
      </radialGradient>
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

    <!-- App icon or default microphone -->
    {#if appIcon}
      <image
        href={appIcon}
        x="16"
        y="16"
        width="32"
        height="32"
        clip-path="url(#iconClip)"
        preserveAspectRatio="xMidYMid slice"
      />
    {:else}
      <!-- Default microphone icon -->
      <g stroke="rgb(220, 220, 220)" stroke-width="2.5" fill="none">
        <!-- Mic body (rounded rect) -->
        <rect x="27" y="20" width="10" height="14" rx="5" ry="5" />
        <!-- Mic arc -->
        <path d="M 24 38 Q 32 44 40 38" />
        <!-- Mic stand -->
        <line x1="32" y1="41" x2="32" y2="46" />
      </g>
    {/if}

    <!-- Status indicator dot glow (breathing effect) -->
    <circle cx="49" cy="49" r="9" fill="url(#glowGradient)" />

    <!-- Status indicator dot -->
    <circle
      cx="49"
      cy="49"
      r="5"
      fill="rgb({currentColor.r}, {currentColor.g}, {currentColor.b})"
      stroke="rgb(40, 40, 45)"
      stroke-width="2"
    />
  </svg>
</div>

<style>
  .orb-container {
    width: 64px;
    height: 64px;
    flex-shrink: 0;
  }
</style>
