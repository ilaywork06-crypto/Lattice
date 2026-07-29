<script setup lang="ts">
/**
 * Lattice's mark: a head of lettuce (חסה) — the product name is one letter away
 * from it, and a lettuce head is layer wrapped around layer, which is exactly
 * what the app tracks (cards inside assemblies inside setups).
 *
 * Each leaf layer is a closed run of equal-radius arcs around uneven anchor
 * points, so the ruffles stay organic instead of reading as a symmetric rosette.
 * Pure SVG, no external asset — it scales and inlines anywhere (favicon too).
 */
withDefaults(defineProps<{ size?: number | string }>(), { size: 40 })
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 64 64"
    fill="none"
    role="img"
    aria-label="Lattice"
    class="brand-logo"
  >
    <!-- outer leaves -->
    <path
      d="M29.73 13.52A9.66 9.66 0 0 1 46.68 16.74A8.98 8.98 0 0 1 53.08 31.45
         A8.78 8.78 0 0 1 49.71 46.76A9.28 9.28 0 0 1 34.16 52.51
         A9.51 9.51 0 0 1 17.32 50.26A8.98 8.98 0 0 1 10.92 35.55
         A8.66 8.66 0 0 1 14.70 20.55A9.29 9.29 0 0 1 29.73 13.52Z"
      fill="#2d7a38"
    />
    <!-- middle leaves -->
    <path
      d="M36.70 20.71A9.37 9.37 0 0 1 46.17 34.50A9.54 9.54 0 0 1 36.87 48.77
         A9.91 9.91 0 0 1 20.28 42.61A9.36 9.36 0 0 1 19.60 25.92
         A10.01 10.01 0 0 1 36.70 20.71Z"
      fill="#4ca54a"
    />
    <!-- heart -->
    <path
      d="M30.13 26.52A5.85 5.85 0 0 1 38.46 32.82A5.86 5.86 0 0 1 32.91 41.68
         A6.02 6.02 0 0 1 24.33 35.22A5.85 5.85 0 0 1 30.13 26.52Z"
      fill="#92cd5c"
    />
    <circle cx="31.5" cy="34" r="2.4" fill="#c9e9a3" />
    <!-- specular highlight, on the r=18 band that clears the middle leaves -->
    <path
      d="M15.09 27.34A18 18 0 0 1 25.84 16.59"
      stroke="#ffffff"
      stroke-opacity="0.26"
      stroke-width="2"
      stroke-linecap="round"
    />
  </svg>
</template>

<style scoped>
.brand-logo {
  display: block;
  flex-shrink: 0;
}
</style>
