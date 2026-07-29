<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title?: string
    message?: string
    confirmText?: string
    color?: string
    icon?: string
    loading?: boolean
    error?: string
  }>(),
  {
    title: '',
    message: '',
    confirmText: '',
    color: 'error',
    icon: 'mdi-alert-circle-outline',
    loading: false,
    error: '',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
}>()

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
</script>

<template>
  <v-dialog v-model="open" max-width="460">
    <v-card rounded="lg">
      <v-card-text class="pa-6 text-center">
        <v-avatar :color="color" variant="tonal" size="64" class="mb-3">
          <v-icon :icon="icon" size="34" />
        </v-avatar>
        <h3 class="text-h6 mb-2">{{ title || $t('dlg.areYouSure') }}</h3>
        <p v-if="message" class="text-body-2 text-medium-emphasis">{{ message }}</p>
        <slot />
        <v-alert
          v-if="error"
          type="error"
          variant="tonal"
          density="compact"
          class="mt-3 text-start"
          :text="error"
        />
      </v-card-text>
      <v-card-actions class="pa-3">
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ $t('common.cancel') }}</v-btn>
        <v-btn :color="color" variant="flat" :loading="loading" @click="emit('confirm')">
          {{ confirmText || $t('common.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
