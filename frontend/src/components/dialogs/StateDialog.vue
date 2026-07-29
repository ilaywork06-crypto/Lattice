<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import StateChip from '@/components/StateChip.vue'
import { ITEM_STATES, STATE_LABELS } from '@/constants'
import type { ItemState } from '@/api/types'

const { t } = useI18n({ useScope: 'global' })

const props = defineProps<{
  modelValue: boolean
  direct: boolean
  currentState: ItemState
  error?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [payload: { state: ItemState; note?: string }]
}>()

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const state = ref<ItemState>(props.currentState)
const note = ref('')
const noteError = ref('')

// A note is required when moving into OR out of the faulty state.
const noteRequired = computed(
  () => state.value === 'faulty' || props.currentState === 'faulty',
)

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      state.value = props.currentState
      note.value = ''
      noteError.value = ''
    }
  },
)

watch(state, () => {
  noteError.value = ''
})

function submit() {
  if (noteRequired.value && !note.value.trim()) {
    noteError.value = t('dlg.state.noteError')
    return
  }
  emit('confirm', { state: state.value, note: note.value.trim() || undefined })
}
</script>

<template>
  <v-dialog v-model="open" max-width="540">
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon icon="mdi-swap-horizontal" color="primary" />
        <span class="text-h6">{{ $t('dlg.state.title') }}</span>
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <div class="d-flex align-center gap-3 mb-4">
          <span class="text-body-2 text-medium-emphasis">{{ $t('dlg.state.current') }}</span>
          <StateChip :state="currentState" />
          <v-icon icon="mdi-arrow-right" size="18" class="text-medium-emphasis flip-rtl" />
          <StateChip :state="state" />
        </div>

        <v-select
          v-model="state"
          :label="$t('dlg.state.newState')"
          :items="ITEM_STATES.map((s) => ({ title: STATE_LABELS[s], value: s }))"
        />

        <v-alert
          v-if="noteRequired"
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-3"
          :text="$t('dlg.state.faultyWarning')"
        />

        <v-textarea
          v-model="note"
          :label="noteRequired ? $t('dlg.noteRequired') : $t('dlg.noteOptional')"
          rows="2"
          auto-grow
          :error="!!noteError"
          :error-messages="noteError"
          @update:model-value="noteError = ''"
        />

        <v-alert v-if="error" type="error" variant="tonal" density="compact" :text="error" />
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-3">
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ $t('common.cancel') }}</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="loading"
          :disabled="state === currentState && direct"
          @click="submit"
        >
          {{ direct ? $t('dlg.state.submit') : $t('dlg.continueToProposal') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
