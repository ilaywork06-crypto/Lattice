<script setup lang="ts">
// Pick one or more catalog field groups (searchable) to load into a template.
import { computed, ref, watch } from 'vue'
import { fieldGroupsApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import { FIELD_TYPE_ICONS, FIELD_TYPE_LABELS } from '@/constants'
import type { FieldGroupOut } from '@/api/types'

const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ load: [groups: FieldGroupOut[]] }>()

const ui = useUiStore()
const groups = ref<FieldGroupOut[]>([])
const loading = ref(false)
const search = ref('')
const picked = ref<number[]>([])

watch(open, async (v) => {
  if (!v) return
  picked.value = []
  search.value = ''
  loading.value = true
  try {
    groups.value = await fieldGroupsApi.list()
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
})

const shown = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return groups.value
  return groups.value.filter(
    (g) =>
      g.name.toLowerCase().includes(q) ||
      (g.description ?? '').toLowerCase().includes(q) ||
      g.fields.some((f) => f.label.toLowerCase().includes(q)),
  )
})

function toggle(id: number) {
  picked.value = picked.value.includes(id)
    ? picked.value.filter((x) => x !== id)
    : [...picked.value, id]
}

function load() {
  // In the order they were picked.
  emit('load', picked.value.map((id) => groups.value.find((g) => g.id === id)!).filter(Boolean))
  open.value = false
}
</script>

<template>
  <v-dialog v-model="open" max-width="640" scrollable>
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon icon="mdi-playlist-plus" color="primary" />
        {{ $t('fieldGroups.pickTitle') }}
      </v-card-title>
      <div class="px-4 pb-2">
        <v-text-field
          v-model="search"
          :placeholder="$t('fieldGroups.searchPlaceholder')"
          prepend-inner-icon="mdi-magnify"
          density="compact"
          hide-details
          clearable
          autofocus
        />
      </div>
      <v-divider />
      <v-card-text class="pa-2" style="max-height: 60vh">
        <div v-if="loading" class="pa-6 text-center">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <div v-else-if="!groups.length" class="pa-6 text-center text-medium-emphasis">
          {{ $t('fieldGroups.noneYet') }}
        </div>
        <div v-else-if="!shown.length" class="pa-6 text-center text-medium-emphasis">
          {{ $t('common.noResults') }}
        </div>
        <v-list v-else density="compact" select-strategy="leaf">
          <v-list-item
            v-for="g in shown"
            :key="g.id"
            :active="picked.includes(g.id)"
            color="primary"
            rounded="lg"
            class="mb-1"
            @click="toggle(g.id)"
          >
            <template #prepend>
              <v-checkbox-btn :model-value="picked.includes(g.id)" @click.stop="toggle(g.id)" />
            </template>
            <v-list-item-title>
              <bdi class="font-weight-medium">{{ g.name }}</bdi>
              <span class="text-caption text-medium-emphasis ms-2">{{ $t('fieldGroups.fieldCount', { n: g.fields.length }) }}</span>
            </v-list-item-title>
            <v-list-item-subtitle v-if="g.description"><bdi>{{ g.description }}</bdi></v-list-item-subtitle>
            <div class="d-flex flex-wrap gap-1 mt-1">
              <v-chip
                v-for="f in g.fields"
                :key="f.key"
                size="x-small"
                variant="tonal"
                :prepend-icon="FIELD_TYPE_ICONS[f.field_type]"
                :title="FIELD_TYPE_LABELS[f.field_type]"
              >
                <bdi>{{ f.label }}</bdi><span v-if="f.required" class="text-error ms-1">*</span>
              </v-chip>
            </div>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-3">
        <span class="text-caption text-medium-emphasis ms-2">{{ $t('fieldGroups.pickHint') }}</span>
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ $t('common.cancel') }}</v-btn>
        <v-btn color="primary" variant="flat" :disabled="!picked.length" @click="load">
          {{ $t('fieldGroups.loadN', { n: picked.length }) }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
