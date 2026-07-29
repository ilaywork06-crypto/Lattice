<script setup lang="ts">
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const icons: Record<string, string> = {
  success: 'mdi-check-circle',
  error: 'mdi-alert-circle',
  warning: 'mdi-alert',
  info: 'mdi-information',
}
</script>

<template>
  <v-snackbar
    v-model="ui.snack.show"
    :color="ui.snack.color"
    :timeout="ui.snack.timeout"
    location="bottom right"
    rounded="lg"
    class="mb-2"
  >
    <div class="d-flex align-center gap-2">
      <v-icon :icon="icons[ui.snack.color]" />
      <span class="text-body-2">{{ ui.snack.message }}</span>
    </div>
    <template #actions>
      <v-btn icon="mdi-close" size="small" variant="text" @click="ui.snack.show = false" />
    </template>
  </v-snackbar>
</template>
