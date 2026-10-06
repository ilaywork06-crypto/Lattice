<script setup lang="ts">
// Catalog → Field groups: named, reusable sets of field definitions that the
// template editor loads in one go. Loading copies the fields, so editing a
// group never changes an existing template.
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fieldGroupsApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import EmptyState from '@/components/EmptyState.vue'
import FieldListEditor from '@/components/FieldListEditor.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import { FIELD_TYPE_ICONS, FIELD_TYPE_LABELS, formatDate } from '@/constants'
import { type FieldRow, cleanFields, rowsFromGroup } from '@/lib/fieldRows'
import type { FieldGroupOut } from '@/api/types'

const { t } = useI18n({ useScope: 'global' })
const auth = useAuthStore()
const ui = useUiStore()

const groups = ref<FieldGroupOut[]>([])
const loading = ref(false)
const search = ref('')

async function load() {
  loading.value = true
  try {
    groups.value = await fieldGroupsApi.list()
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

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

// ── create / edit ──
const dialog = ref(false)
const editing = ref<FieldGroupOut | null>(null)
const form = reactive<{ name: string; description: string; fields: FieldRow[] }>({
  name: '',
  description: '',
  fields: [],
})
const saving = ref(false)

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', description: '', fields: [] })
  dialog.value = true
}

function openEdit(g: FieldGroupOut) {
  editing.value = g
  Object.assign(form, { name: g.name, description: g.description ?? '', fields: rowsFromGroup(g.fields) })
  dialog.value = true
}

async function save() {
  if (!form.name.trim()) {
    ui.warning(t('fieldGroups.nameRequired'))
    return
  }
  if (form.fields.some((f) => !f.label.trim())) {
    ui.warning(t('tplEditor.fieldNameRequired'))
    return
  }
  const body = {
    name: form.name.trim(),
    description: form.description.trim() || null,
    fields: cleanFields(form.fields, false),
  }
  saving.value = true
  try {
    if (editing.value) await fieldGroupsApi.update(editing.value.id, body)
    else await fieldGroupsApi.create(body)
    ui.success(t('fieldGroups.saved', { name: body.name }))
    dialog.value = false
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    saving.value = false
  }
}

// ── delete ──
const deleting = ref<FieldGroupOut | null>(null)
const deleteOpen = computed({
  get: () => !!deleting.value,
  set: (v: boolean) => {
    if (!v) deleting.value = null
  },
})
async function remove() {
  if (!deleting.value) return
  try {
    await fieldGroupsApi.remove(deleting.value.id)
    ui.success(t('fieldGroups.deleted'))
    deleting.value = null
    await load()
  } catch (e) {
    ui.error(e)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <v-alert type="info" variant="tonal" density="compact" class="ma-4" icon="mdi-form-select">
      {{ $t('fieldGroups.explainer') }}
    </v-alert>
    <div class="px-4 pb-3 d-flex align-center gap-3 flex-wrap">
      <v-text-field
        v-model="search"
        :placeholder="$t('fieldGroups.searchPlaceholder')"
        prepend-inner-icon="mdi-magnify"
        clearable
        hide-details
        density="comfortable"
        style="max-width: 340px"
      />
      <v-spacer />
      <v-btn v-if="auth.canDirectEdit" color="primary" prepend-icon="mdi-plus" @click="openCreate">
        {{ $t('fieldGroups.new') }}
      </v-btn>
    </div>

    <div v-if="loading && !groups.length" class="pa-6 text-center">
      <v-progress-circular indeterminate color="primary" />
    </div>
    <EmptyState
      v-else-if="!shown.length"
      icon="mdi-form-select"
      :title="groups.length ? $t('common.noResults') : $t('fieldGroups.noneYet')"
      :text="groups.length ? undefined : $t('fieldGroups.noneYetHint')"
    />
    <v-row v-else class="px-4 pb-4" dense>
      <v-col v-for="g in shown" :key="g.id" cols="12" md="6" lg="4">
        <v-card variant="outlined" class="h-100">
          <v-card-title class="d-flex align-center gap-2">
            <v-icon icon="mdi-form-select" color="primary" size="20" />
            <bdi class="text-truncate">{{ g.name }}</bdi>
            <v-spacer />
            <template v-if="auth.canDirectEdit">
              <v-btn icon="mdi-pencil" size="x-small" variant="text" :aria-label="$t('common.edit')" @click="openEdit(g)" />
              <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error" :aria-label="$t('common.delete')" @click="deleting = g" />
            </template>
          </v-card-title>
          <v-card-subtitle v-if="g.description"><bdi>{{ g.description }}</bdi></v-card-subtitle>
          <v-card-text>
            <div class="d-flex flex-wrap gap-1">
              <v-chip
                v-for="f in g.fields"
                :key="f.key"
                size="small"
                variant="tonal"
                :prepend-icon="FIELD_TYPE_ICONS[f.field_type]"
                :title="FIELD_TYPE_LABELS[f.field_type]"
              >
                <bdi>{{ f.label }}</bdi><span v-if="f.required" class="text-error ms-1">*</span>
              </v-chip>
            </div>
            <div class="text-caption text-medium-emphasis mt-3">
              {{ $t('fieldGroups.fieldCount', { n: g.fields.length }) }} · {{ formatDate(g.updated_at) }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="dialog" max-width="980" scrollable>
      <v-card rounded="lg">
        <v-card-title class="d-flex align-center gap-2 pa-4">
          <v-icon icon="mdi-form-select" color="primary" />
          {{ editing ? $t('fieldGroups.editTitle', { name: editing.name }) : $t('fieldGroups.new') }}
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4" style="max-height: 74vh">
          <v-row dense>
            <v-col cols="12" sm="5">
              <v-text-field v-model="form.name" :label="$t('fieldGroups.name')" />
            </v-col>
            <v-col cols="12" sm="7">
              <v-text-field v-model="form.description" :label="$t('fields.description')" />
            </v-col>
          </v-row>
          <div class="text-caption text-medium-emphasis">{{ $t('fieldGroups.editHint') }}</div>
          <FieldListEditor v-model="form.fields" :item-type="null" />
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" prepend-icon="mdi-content-save" :loading="saving" @click="save">
            {{ $t('common.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ConfirmDialog
      v-model="deleteOpen"
      :title="$t('fieldGroups.deleteTitle')"
      :message="$t('fieldGroups.deleteMsg', { name: deleting?.name ?? '' })"
      :confirm-text="$t('common.delete')"
      color="error"
      icon="mdi-delete-alert"
      @confirm="remove"
    />
  </div>
</template>
