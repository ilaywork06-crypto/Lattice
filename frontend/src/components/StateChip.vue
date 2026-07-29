<script setup lang="ts">
import { computed } from 'vue'
import type { ItemState } from '@/api/types'
import { STATE_COLORS, STATE_LABELS } from '@/constants'

const props = withDefaults(
  defineProps<{ state: ItemState | null | undefined; size?: string }>(),
  { size: 'small' },
)

const color = computed(() => (props.state ? STATE_COLORS[props.state] : 'grey'))
const label = computed(() => (props.state ? STATE_LABELS[props.state] : '—'))
const icon = computed(() => (props.state === 'faulty' ? 'mdi-alert' : undefined))
</script>

<template>
  <v-chip :color="color" :size="size" variant="flat" label class="font-weight-medium">
    <v-icon v-if="icon" :icon="icon" start size="14" />
    {{ label }}
  </v-chip>
</template>
