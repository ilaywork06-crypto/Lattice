<script setup lang="ts">
withDefaults(
  defineProps<{ title: string; subtitle?: string; icon?: string }>(),
  { subtitle: '', icon: '' },
)
</script>

<template>
  <div class="d-flex flex-wrap align-center justify-space-between mb-5 gap-3">
    <div class="d-flex align-center gap-3">
      <v-avatar v-if="icon" color="primary" variant="tonal" rounded="lg" size="44">
        <v-icon :icon="icon" size="24" />
      </v-avatar>
      <div>
        <h1 class="text-h5 font-weight-bold" style="line-height: 1.2">{{ title }}</h1>
        <div v-if="subtitle" class="text-body-2 text-medium-emphasis">{{ subtitle }}</div>
      </div>
    </div>
    <div class="d-flex align-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
