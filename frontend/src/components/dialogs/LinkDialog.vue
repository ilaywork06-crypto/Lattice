<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { itemsApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import { TYPE_LABELS } from '@/constants'
import type { ItemType } from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  direct: boolean
  itemId: number
  itemType: ItemType
  error?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [payload: { parent_id: number }]
}>()

const ui = useUiStore()
const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const parentType = computed<ItemType | null>(() => {
  if (props.itemType === 'card') return 'assembly'
  if (props.itemType === 'assembly') return 'setup'
  return null
})

const parents = ref<{ id: number; name: string }[]>([])
const parentId = ref<number | null>(null)
const loadingList = ref(false)
const parentError = ref(false)

watch(
  () => props.modelValue,
  async (v) => {
    if (v && parentType.value) {
      parentId.value = null
      parentError.value = false
      loadingList.value = true
      try {
        const items = await itemsApi.list({ type: parentType.value, limit: 500 })
        parents.value = items
          .filter((i) => i.id !== props.itemId)
          .map((i) => ({ id: i.id, name: i.name }))
      } catch (e) {
        ui.error(e)
      } finally {
        loadingList.value = false
      }
    }
  },
)

function submit() {
  if (!parentId.value) {
    parentError.value = true
    return
  }
  emit('confirm', { parent_id: parentId.value })
}
</script>

<template>
  <v-dialog v-model="open" max-width="520">
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon icon="mdi-link-variant" color="primary" />
        <span class="text-h6">{{ $t('dlg.link.title') }}</span>
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <template v-if="parentType">
          <v-autocomplete
            v-model="parentId"
            :label="$t('dlg.link.parentLabel', { type: TYPE_LABELS[parentType] })"
            :items="parents.map((p) => ({ title: p.name, value: p.id }))"
            :loading="loadingList"
            :error="parentError"
            :error-messages="parentError ? $t('dlg.link.chooseParent') : ''"
            @update:model-value="parentError = false"
          />
          <v-alert v-if="error" type="error" variant="tonal" density="compact" :text="error" />
        </template>
        <v-alert
          v-else
          type="info"
          variant="tonal"
          density="compact"
          :text="$t('dlg.link.setupInfo')"
        />
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-3">
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ $t('common.cancel') }}</v-btn>
        <v-btn
          v-if="parentType"
          color="primary"
          variant="flat"
          :loading="loading"
          @click="submit"
        >
          {{ direct ? $t('dlg.link.submit') : $t('dlg.continueToProposal') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
