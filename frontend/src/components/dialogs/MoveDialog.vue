<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { locationsApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import type { LocationOut } from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  direct: boolean
  currentLocationId?: number | null
  error?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [payload: { location_id: number; note?: string }]
}>()

const ui = useUiStore()
const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const locations = ref<LocationOut[]>([])
const locationId = ref<number | null>(null)
const note = ref('')
const locError = ref(false)

watch(
  () => props.modelValue,
  async (v) => {
    if (v) {
      locationId.value = props.currentLocationId ?? null
      note.value = ''
      locError.value = false
      try {
        locations.value = await locationsApi.list()
      } catch (e) {
        ui.error(e)
      }
    }
  },
)

function submit() {
  if (!locationId.value) {
    locError.value = true
    return
  }
  emit('confirm', { location_id: locationId.value, note: note.value.trim() || undefined })
}
</script>

<template>
  <v-dialog v-model="open" max-width="520">
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon icon="mdi-map-marker-radius" color="primary" />
        <span class="text-h6">{{ $t('dlg.move.title') }}</span>
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <p class="text-body-2 text-medium-emphasis mb-4">
          {{ $t('dlg.move.desc') }}
        </p>
        <v-select
          v-model="locationId"
          :label="$t('dlg.move.destination')"
          :items="locations.map((l) => ({ title: l.name, value: l.id, subtitle: l.building }))"
          :error="locError"
          :error-messages="locError ? $t('dlg.move.selectDest') : ''"
          @update:model-value="locError = false"
        />
        <v-textarea v-model="note" :label="$t('dlg.noteOptional')" rows="2" auto-grow />
        <v-alert v-if="error" type="error" variant="tonal" density="compact" :text="error" />
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-3">
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ $t('common.cancel') }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="loading" @click="submit">
          {{ direct ? $t('dlg.move.submit') : $t('dlg.continueToProposal') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
