<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { itemsApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import { TYPE_LABELS } from '@/constants'
import type { ItemListOut, ItemType } from '@/api/types'

// Parents on offer are exactly the items whose template lists this item's
// template as allowed contents — a card can go into a setup as well as an
// assembly when the templates say so (the old dialog only offered assemblies).
const props = defineProps<{
  modelValue: boolean
  direct: boolean
  itemId: number
  itemType: ItemType
  templateId: number
  error?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [payload: { parent_id: number; parent_label?: string }]
}>()

const ui = useUiStore()
const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const parents = ref<ItemListOut[]>([])
const parentId = ref<number | null>(null)
const loadingList = ref(false)
const parentError = ref(false)

watch(
  () => props.modelValue,
  async (v) => {
    if (!v || props.itemType === 'setup') return
    parentId.value = null
    parentError.value = false
    loadingList.value = true
    try {
      parents.value = (
        await itemsApi.list({ parent_of_template: props.templateId, include_destroyed: false })
      ).filter((i) => i.id !== props.itemId)
    } catch (e) {
      ui.error(e)
    } finally {
      loadingList.value = false
    }
  },
)

const choices = computed(() =>
  parents.value.map((p) => ({
    title: `${p.name} · ${p.serial}`,
    value: p.id,
    subtitle: `${TYPE_LABELS[p.type]}${p.location_name ? ' · ' + p.location_name : ''}`,
  })),
)

function submit() {
  if (!parentId.value) {
    parentError.value = true
    return
  }
  const chosen = choices.value.find((c) => c.value === parentId.value)
  emit('confirm', { parent_id: parentId.value, parent_label: chosen?.title })
}
</script>

<template>
  <v-dialog v-model="open" max-width="560">
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon icon="mdi-link-variant" color="primary" />
        <span class="text-h6">{{ $t('dlg.link.title') }}</span>
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <template v-if="itemType !== 'setup'">
          <v-autocomplete
            v-model="parentId"
            :label="$t('dlg.link.parentAny')"
            :items="choices"
            item-title="title"
            item-value="value"
            :loading="loadingList"
            :error="parentError"
            :error-messages="parentError ? $t('dlg.link.chooseParent') : ''"
            :no-data-text="$t('dlg.link.noParents')"
            @update:model-value="parentError = false"
          >
            <template #item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
            </template>
          </v-autocomplete>
          <v-alert v-if="error" type="error" variant="tonal" density="compact" :text="error" />
        </template>
        <v-alert v-else type="info" variant="tonal" density="compact" :text="$t('dlg.link.setupInfo')" />
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-3">
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ $t('common.cancel') }}</v-btn>
        <v-btn v-if="itemType !== 'setup'" color="primary" variant="flat" :loading="loading" @click="submit">
          {{ direct ? $t('dlg.link.submit') : $t('dlg.continueToProposal') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
