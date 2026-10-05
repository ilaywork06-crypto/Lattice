<script setup lang="ts">
// Create an item from its template, or edit an item's own values.
//
// Everything about the form comes from the template: grey fields are filled
// in here, list fields offer the template's values (the first preselected),
// and white fields are shown read-only — they are the template's, shared by
// every item made from it. Managers save directly; anyone else's form turns
// into a change-request proposal.
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { extractErrorList } from '@/api/client'
import { itemsApi, templatesApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import FieldInput from '@/components/FieldInput.vue'
import { CARD_TYPE_LABELS, TYPE_LABELS } from '@/constants'
import type {
  ItemCreate,
  ItemListOut,
  ItemOut,
  ItemType,
  ItemUpdate,
  TemplateFieldOut,
  TemplateOut,
  TemplateSummary,
} from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  mode: 'create' | 'edit'
  /** create: which kind of template to pick from (when no template is given) */
  type?: ItemType | null
  /** create: start from this template */
  templateId?: number | null
  /** edit: the item */
  item?: ItemOut | null
  direct: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [item: ItemOut]
  propose: [payload: ItemCreate | ItemUpdate, template: TemplateOut]
}>()

const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const templates = ref<TemplateSummary[]>([])
const chosenId = ref<number | null>(null)
const template = ref<TemplateOut | null>(null)
const loadingTpl = ref(false)
const values = reactive<Record<string, unknown>>({})
const original = ref<Record<string, unknown>>({})
const serial = ref('')
const childIds = ref<number[]>([])
const childOptions = ref<ItemListOut[]>([])
const fieldErrors = ref<Record<string, string>>({})
const formRef = ref()
const saving = ref(false)

// Physical state has its own actions on the item page.
const ACTION_ONLY = ['location', 'parent', 'status']

const editableFields = computed<TemplateFieldOut[]>(() => {
  const fields = template.value?.fields ?? []
  return fields.filter((f) => {
    if (f.mode === 'fixed') return false
    if (props.mode === 'edit' && ACTION_ONLY.includes(f.field_type)) return false
    return true
  })
})
const fixedFields = computed(() => (template.value?.fields ?? []).filter((f) => f.mode === 'fixed'))

function fieldDefault(f: TemplateFieldOut): unknown {
  if (f.mode === 'choice') {
    const first = (f.config.options ?? [])[0]
    if (first === undefined) return null
    return f.field_type === 'managers' ? [first] : first
  }
  if (f.field_type === 'boolean') return false
  if (f.field_type === 'managers' || f.field_type === 'files') return []
  return null
}

async function loadTemplate(id: number | null) {
  template.value = null
  Object.keys(values).forEach((k) => delete values[k])
  fieldErrors.value = {}
  if (!id) return
  loadingTpl.value = true
  try {
    template.value = await templatesApi.get(id)
    if (props.mode === 'edit' && props.item) {
      for (const f of props.item.fields) values[f.key] = f.value
      original.value = JSON.parse(JSON.stringify(values))
      serial.value = props.item.serial
    } else {
      for (const f of template.value.fields) {
        if (f.mode !== 'fixed') values[f.key] = fieldDefault(f)
      }
      serial.value = ''
      childIds.value = []
      if (template.value.child_templates.length) {
        childOptions.value = (await itemsApi.list({
          child_of_template: id,
          include_destroyed: false,
        })).sort((a, b) => Number(!!a.parent_id) - Number(!!b.parent_id) || a.serial.localeCompare(b.serial))
      } else {
        childOptions.value = []
      }
    }
  } catch (e) {
    ui.error(e)
  } finally {
    loadingTpl.value = false
  }
}

watch(
  () => props.modelValue,
  async (v) => {
    if (!v) return
    fieldErrors.value = {}
    if (props.mode === 'edit' && props.item) {
      chosenId.value = props.item.template.id
      await loadTemplate(props.item.template.id)
      return
    }
    chosenId.value = props.templateId ?? null
    try {
      templates.value = await templatesApi.list(props.type ? { type: props.type } : {})
    } catch (e) {
      ui.error(e)
    }
    if (!chosenId.value && templates.value.length === 1) chosenId.value = templates.value[0].id
    await loadTemplate(chosenId.value)
  },
)

watch(chosenId, (id) => {
  if (props.mode === 'create' && id !== template.value?.id) void loadTemplate(id)
})

const templateChoices = computed(() =>
  templates.value.map((tp) => ({
    title: tp.name,
    value: tp.id,
    subtitle: [TYPE_LABELS[tp.type], tp.card_type ? CARD_TYPE_LABELS[tp.card_type] : null, tp.serial_prefix]
      .filter(Boolean)
      .join(' · '),
  })),
)

const childChoices = computed(() =>
  childOptions.value.map((c) => ({
    title: `${c.name} · ${c.serial}`,
    value: c.id,
    subtitle: c.parent_id ? t('itemForm.willMove', { from: c.parent_label }) : c.location_name ?? '',
  })),
)

function display(f: TemplateFieldOut): string {
  const d = f.fixed_display
  if (d === null || d === undefined || d === '') return '—'
  if (Array.isArray(d)) return d.map((x) => (typeof x === 'object' && x ? (x as { name: string }).name : String(x))).join(', ')
  if (typeof d === 'boolean') return d ? t('common.yes') : t('common.no')
  return String(d)
}

function changedValues(): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of editableFields.value) {
    const now = values[f.key]
    if (JSON.stringify(now ?? null) !== JSON.stringify(original.value[f.key] ?? null)) out[f.key] = now
  }
  return out
}

async function submit() {
  const res = await formRef.value?.validate()
  if (res && !res.valid) return
  if (!template.value) return
  fieldErrors.value = {}

  let payload: ItemCreate | ItemUpdate
  if (props.mode === 'create') {
    const vals: Record<string, unknown> = {}
    for (const f of editableFields.value) vals[f.key] = values[f.key]
    payload = {
      template_id: template.value.id,
      values: vals,
      serial: serial.value.trim() || null,
      child_ids: childIds.value,
    }
  } else {
    payload = { values: changedValues() }
    if (serial.value.trim() && serial.value.trim().toUpperCase() !== props.item?.serial) {
      payload.serial = serial.value.trim()
    }
    if (!Object.keys(payload.values ?? {}).length && !payload.serial) {
      open.value = false
      return
    }
  }

  if (!props.direct) {
    emit('propose', payload, template.value)
    open.value = false
    return
  }
  saving.value = true
  try {
    const saved =
      props.mode === 'create'
        ? await itemsApi.create(payload as ItemCreate)
        : await itemsApi.update(props.item!.id, payload as ItemUpdate)
    emit('saved', saved)
    open.value = false
  } catch (e) {
    const list = extractErrorList(e)
    if (list.length) {
      fieldErrors.value = Object.fromEntries(
        list.filter((x) => x.field).map((x) => [x.field as string, x.error]),
      )
    }
    ui.error(e)
  } finally {
    saving.value = false
  }
}

const dialogTitle = computed(() => {
  if (props.mode === 'edit') return t('itemForm.editOf', { name: `${props.item?.name} · ${props.item?.serial}` })
  if (template.value) return t('itemForm.newFrom', { name: template.value.name })
  return t('itemForm.newOf', { type: props.type ? TYPE_LABELS[props.type] : t('itemForm.item') })
})
</script>

<template>
  <v-dialog v-model="open" max-width="780" scrollable>
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon :icon="mode === 'create' ? 'mdi-plus-circle' : 'mdi-pencil'" color="primary" />
        <span class="text-h6">{{ dialogTitle }}</span>
      </v-card-title>
      <v-divider />

      <v-card-text class="pa-4" style="max-height: 70vh">
        <v-form ref="formRef" @submit.prevent="submit">
          <!-- 1. the template (items are only ever made from one) -->
          <v-autocomplete
            v-if="mode === 'create'"
            v-model="chosenId"
            :label="$t('itemForm.template')"
            :items="templateChoices"
            item-title="title"
            item-value="value"
            prepend-inner-icon="mdi-shape-outline"
            :rules="[(v: unknown) => !!v || $t('common.required')]"
            :no-data-text="$t('itemForm.noTemplates')"
            :hint="$t('itemForm.templateHint')"
            persistent-hint
            class="mb-3"
          >
            <template #item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
            </template>
          </v-autocomplete>

          <v-progress-linear v-if="loadingTpl" indeterminate color="primary" class="mb-3" />

          <template v-if="template">
            <!-- the template's own (white) values -->
            <div v-if="fixedFields.length" class="fixed-box mb-4">
              <div class="text-overline text-medium-emphasis mb-1">{{ $t('itemForm.fromTemplate') }}</div>
              <div class="d-flex flex-wrap gap-2">
                <v-chip v-for="f in fixedFields" :key="f.id" size="small" variant="outlined" label>
                  <span class="text-medium-emphasis me-1">{{ f.label }}:</span> {{ display(f) }}
                </v-chip>
              </div>
            </div>

            <!-- serial -->
            <v-text-field
              v-model="serial"
              :label="mode === 'create' ? $t('itemForm.serialAuto') : $t('fields.serial')"
              :placeholder="mode === 'create' ? template.next_serial ?? '' : undefined"
              :hint="mode === 'create' ? $t('itemForm.serialAutoHint', { next: template.next_serial }) : $t('itemForm.serialEditHint')"
              persistent-hint
              prepend-inner-icon="mdi-barcode"
              class="mb-3"
              @update:model-value="(v: string) => (serial = (v || '').toUpperCase())"
            />

            <!-- the per-item and list fields -->
            <div v-if="editableFields.length" class="text-overline text-medium-emphasis">
              {{ $t('itemForm.itemFields') }}
            </div>
            <FieldInput
              v-for="f in editableFields"
              :key="f.id"
              v-model="values[f.key]"
              :field="f"
              :template-id="template.id"
              :files="item?.fields.find((x) => x.key === f.key)?.display as any"
              :error-messages="fieldErrors[f.key] ? [fieldErrors[f.key]] : []"
            />
            <v-alert
              v-if="!editableFields.length && mode === 'create'"
              type="info"
              variant="tonal"
              density="compact"
              class="mb-3"
            >
              {{ $t('itemForm.nothingToFill') }}
            </v-alert>

            <!-- contents (containers) -->
            <v-autocomplete
              v-if="mode === 'create' && template.child_templates.length"
              v-model="childIds"
              :label="$t('itemForm.contents')"
              :items="childChoices"
              item-title="title"
              item-value="value"
              multiple
              chips
              closable-chips
              prepend-inner-icon="mdi-file-tree-outline"
              :hint="$t('itemForm.contentsHint', { names: template.child_templates.map((c) => c.name).join(', ') })"
              persistent-hint
              class="mt-2"
            >
              <template #item="{ props: itemProps, item }">
                <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
              </template>
            </v-autocomplete>
          </template>
        </v-form>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-3">
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ $t('common.cancel') }}</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="saving"
          :disabled="!template"
          :prepend-icon="direct ? 'mdi-content-save' : 'mdi-send'"
          @click="submit"
        >
          {{ direct ? (mode === 'create' ? $t('common.create') : $t('common.save')) : $t('dlg.continueToProposal') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.fixed-box {
  border: 1px dashed rgba(var(--v-border-color), 0.5);
  border-radius: 10px;
  padding: 8px 12px;
}
</style>
