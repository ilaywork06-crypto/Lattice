<script setup lang="ts">
withDefaults(
  defineProps<{ icon?: string; title?: string; text?: string }>(),
  {
    icon: 'mdi-inbox-outline',
    title: '',
    text: '',
  },
)
</script>

<template>
  <div class="d-flex flex-column align-center justify-center text-center pa-8">
    <v-avatar size="72" color="surface-variant" class="mb-4">
      <v-icon :icon="icon" size="36" color="on-surface-variant" />
    </v-avatar>
    <div class="text-subtitle-1 font-weight-medium">{{ title || $t('emptyDefault') }}</div>
    <div v-if="text" class="text-body-2 text-medium-emphasis mt-1" style="max-width: 420px">
      {{ text }}
    </div>
    <slot />
  </div>
</template>
