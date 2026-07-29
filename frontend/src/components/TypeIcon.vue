<script setup lang="ts">
import { computed } from 'vue'
import type { ItemType } from '@/api/types'
import { TYPE_COLORS, TYPE_ICONS, TYPE_LABELS } from '@/constants'

const props = withDefaults(
  defineProps<{ type: ItemType; withLabel?: boolean; size?: string | number }>(),
  { withLabel: false, size: 20 },
)

const icon = computed(() => TYPE_ICONS[props.type])
const color = computed(() => TYPE_COLORS[props.type])
const label = computed(() => TYPE_LABELS[props.type])
</script>

<template>
  <span class="d-inline-flex align-center gap-2">
    <v-icon :icon="icon" :color="color" :size="size" />
    <span v-if="withLabel">{{ label }}</span>
  </span>
</template>
