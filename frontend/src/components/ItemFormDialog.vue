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
import { CARD_TYPE_LABELS, TYPE_LABELS, fieldLabel } from '@/constants'
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
import { isolate } from '@/utils/bidi'

const props = defineProps<{
  modelValue: boolean
  mode: 'create' | 'edit'
  /** create: which kind of template to pick from (when no template is given) */
  type?: ItemType | null
  /** create: start from this template */
  templateId?: number | null
  /** edit: the item */
  item?: ItemOut | null
  /** create: preselect the item to place the new one inside */
  parentId?: number | null
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
// Where the new item goes: an item whose template lists this one as contents.
const parentId = ref<number | null>(null)
const parentOptions = ref<ItemListOut[]>([])
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
      parentId.value = props.parentId ?? null
      const [children, parents] = await Promise.all([
        template.value.child_templates.length
          ? itemsApi.list({ child_of_template: id, include_destroyed: false })
          : Promise.resolve([] as ItemListOut[]),
        template.value.parent_templates.length && !hasParentField.value
          ? itemsApi.list({ parent_of_template: id, include_destroyed: false })
          : Promise.resolve([] as ItemListOut[]),
      ])
      childOptions.value = children.sort(
        (a, b) => Number(!!a.parent_id) - Number(!!b.parent_id) || a.serial.localeCompare(b.serial),
      )
      parentOptions.value = parents
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

// A template with its own "parent" field picks the parent there.
const hasParentField = computed(
  () => !!template.value?.fields.some((f) => f.field_type === 'parent' && f.mode !== 'fixed'),
)
const showParentPicker = computed(
  () => props.mode === 'create' && !!template.value?.parent_templates.length && !hasParentField.value,
)
const showLinks = computed(
  () => props.mode === 'create' && !!template.value && (showParentPicker.value || !!template.value.child_templates.length),
)

const parentChoices = computed(() =>
  parentOptions.value.map((p) => ({
    title: `${p.name} · ${p.serial}`,
    value: p.id,
    subtitle: `${TYPE_LABELS[p.type]}${p.location_name ? ' · ' + isolate(p.location_name) : ''}`,
    missing: p.missing_children,
  })),
)

// Contents against the template's limits, per child template.
const limitRows = computed(() =>
  (template.value?.children ?? []).map((c) => {
    const count = childOptions.value.filter(
      (o) => childIds.value.includes(o.id) && o.template_id === c.template.id,
    ).reduce((n, o) => n + (o.quantity || 1), 0)
    return { ...c, count, over: c.max_count != null && count > c.max_count, short: Math.max(c.min_count - count, 0) }
  }),
)
const overLimit = computed(() => limitRows.value.filter((r) => r.over))
function limitText(min: number, max: number | null): string {
  if (max == null) return min ? t('templates.limitAtLeast', { min }) : t('templates.limitNone')
  if (min === max) return t('templates.limitExactly', { n: min })
  return t('templates.limitRange', { min, max })
}

const childChoices = computed(() =>
  childOptions.value.map((c) => ({
    title: `${c.name} · ${c.serial}`,
    value: c.id,
    subtitle: c.parent_id ? t('itemForm.willMove', { from: c.parent_label }) : c.location_name ? isolate(c.location_name) : '',
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

  if (props.mode === 'create' && overLimit.value.length) {
    ui.warning(t('itemForm.overLimit', { names: overLimit.value.map((r) => r.template.name).join(', ') }))
    return
  }

  let payload: ItemCreate | ItemUpdate
  if (props.mode === 'create') {
    const vals: Record<string, unknown> = {}
    for (const f of editableFields.value) vals[f.key] = values[f.key]
    payload = {
      template_id: template.value.id,
      values: vals,
      serial: serial.value.trim() || null,
      child_ids: childIds.value,
      parent_id: showParentPicker.value ? parentId.value : null,
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
                  <span class="text-medium-emphasis me-1"><bdi>{{ fieldLabel(f) }}</bdi>:</span> {{ display(f) }}
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

            <!-- links: where it goes, and what goes inside it -->
            <template v-if="showLinks">
              <div class="text-overline text-medium-emphasis mt-2">{{ $t('itemForm.links') }}</div>
              <v-autocomplete
                v-if="showParentPicker"
                v-model="parentId"
                :label="$t('itemForm.parent')"
                :items="parentChoices"
                item-title="title"
                item-value="value"
                clearable
                prepend-inner-icon="mdi-link-variant"
                :no-data-text="$t('itemForm.noParents')"
                :hint="$t('itemForm.parentHint', { names: template.parent_templates.map((p) => p.name).join(', ') })"
                persistent-hint
                class="mb-3"
              >
                <template #item="{ props: itemProps, item }">
                  <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle">
                    <template v-if="item.raw.missing" #append>
                      <v-chip size="x-small" color="warning" variant="tonal">
                        {{ $t('detail.missingN', { n: item.raw.missing }) }}
                      </v-chip>
                    </template>
                  </v-list-item>
                </template>
              </v-autocomplete>

              <template v-if="template.child_templates.length">
                <v-autocomplete
                  v-model="childIds"
                  :label="$t('itemForm.contents')"
                  :items="childChoices"
                  item-title="title"
                  item-value="value"
                  multiple
                  chips
                  closable-chips
                  prepend-inner-icon="mdi-file-tree-outline"
                  :no-data-text="$t('itemForm.noChildren')"
                  :error-messages="overLimit.length ? [$t('itemForm.overLimit', { names: overLimit.map((r) => r.template.name).join(', ') })] : []"
                  :hint="$t('itemForm.contentsHint', { names: template.child_templates.map((c) => c.name).join(', ') })"
                  persistent-hint
                >
                  <template #item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
                  </template>
                </v-autocomplete>
                <div v-if="limitRows.some((r) => r.min_count || r.max_count != null)" class="d-flex flex-wrap gap-2 mt-2">
                  <v-chip
                    v-for="r in limitRows"
                    :key="r.template.id"
                    size="small"
                    variant="tonal"
                    :color="r.over ? 'error' : r.short ? 'warning' : 'success'"
                  >
                    <bdi>{{ r.template.name }}</bdi>: {{ r.count }} · {{ limitText(r.min_count, r.max_count) }}
                  </v-chip>
                </div>
              </template>
            </template>
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
