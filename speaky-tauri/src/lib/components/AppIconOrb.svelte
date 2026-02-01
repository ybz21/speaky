<script lang="ts">
  import { onDestroy } from "svelte";

  export let audioLevel: number = 0;
  export let mode: string = "idle";
  export let appIcon: string | null = null;
  export let animating: boolean = false;

  $: if (appIcon) {
    console.log("AppIconOrb received icon, length:", appIcon.length, "starts with:", appIcon.substring(0, 50));
  }

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
  <!-- App icon (outside SVG for better compatibility) -->
  {#if appIcon}
    <div class="icon-wrapper">
      <img src={appIcon} alt="app" class="app-icon" />
    </div>
  {:else}
    <div class="icon-wrapper default-icon">
      <svg width="32" height="32" viewBox="0 0 32 32">
        <g stroke="rgb(220, 220, 220)" stroke-width="2" fill="none">
          <rect x="11" y="6" width="10" height="12" rx="5" ry="5" />
          <path d="M 8 20 Q 16 26 24 20" />
          <line x1="16" y1="23" x2="16" y2="28" />
        </g>
      </svg>
    </div>
  {/if}

  <!-- Status indicator -->
  <div
    class="status-dot"
    style="background: rgb({currentColor.r}, {currentColor.g}, {currentColor.b}); box-shadow: 0 0 8px rgba({currentColor.r}, {currentColor.g}, {currentColor.b}, {glowAlpha});"
  ></div>
</div>

<style>
  .orb-container {
    width: 64px;
    height: 64px;
    flex-shrink: 0;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .icon-wrapper {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: linear-gradient(135deg, rgba(70, 70, 75, 0.98) 0%, rgba(40, 40, 45, 0.98) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(255, 255, 255, 0.1);
    overflow: hidden;
  }

  .app-icon {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    object-fit: cover;
  }

  .default-icon {
    padding: 8px;
  }

  .status-dot {
    position: absolute;
    bottom: 4px;
    right: 4px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 2px solid rgb(40, 40, 45);
  }
</style>
