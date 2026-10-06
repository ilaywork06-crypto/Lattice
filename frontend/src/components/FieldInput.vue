<script setup lang="ts">
// One input for one template field, whatever its type.
//
// Used in three places: filling an item (`mode="value"`), setting a template's
// fixed value (also `"value"`), and defining a list field's allowed values
// (`mode="options"`, always a multi-select of that type's values).
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { documentsApi, itemsApi } from '@/api/services'
import { useCatalogStore } from '@/stores/catalog'
import { useRefsStore } from '@/stores/refs'
import { useUiStore } from '@/stores/ui'
import {
  FIELD_TYPE_ICONS,
  ITEM_STATES,
  LETTERS,
  STATE_LABELS,
  applyPattern,
  formatBytes,
  formatDate,
  parseDay,
  toDay,
} from '@/constants'
import type {
  DocumentOut,
  FieldConfig,
  FieldMode,
  FieldType,
  ItemListOut,
} from '@/api/types'

export interface FieldMeta {
  key?: string | null
  label: string
  field_type: FieldType
  mode: FieldMode
  required: boolean
  config: FieldConfig
  options_display?: string[]
}

const props = withDefaults(
  defineProps<{
    field: FieldMeta
    modelValue: unknown
    mode?: 'value' | 'options'
    /** The template an item is being made from (parent candidates). */
    templateId?: number | null
    /** Files already attached (display only — the value holds their ids). */
    files?: DocumentOut[]
    disabled?: boolean
    errorMessages?: string | string[]
    hideLabel?: boolean
  }>(),
  { mode: 'value', templateId: null, files: () => [], disabled: false, errorMessages: () => [] },
)

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n({ useScope: 'global' })
const catalog = useCatalogStore()
const refs = useRefsStore()
const ui = useUiStore()

const ft = computed(() => props.field.field_type)
const isOptions = computed(() => props.mode === 'options')
// A list field (or an enum) offers exactly the template's values.
const fromList = computed(
  () => !isOptions.value && (props.field.mode === 'choice' || ft.value === 'enum'),
)
const label = computed(() =>
  props.hideLabel ? undefined : props.field.label + (props.field.required && !isOptions.value ? ' *' : ''),
)
const icon = computed(() => FIELD_TYPE_ICONS[ft.value])

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const value = computed<any>({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// ── date (stored as "YYYY-MM-DD") ──
const dateMenu = ref(false)
function pickDate(d: unknown) {
  if (d instanceof Date) value.value = toDay(d)
  dateMenu.value = false
}

// ── reference lists ──
const parentItems = ref<ItemListOut[]>([])
const loadingParents = ref(false)

async function loadParents() {
  if (ft.value !== 'parent' || !props.templateId) return
  loadingParents.value = true
  try {
    parentItems.value = await itemsApi.list({
      parent_of_template: props.templateId,
      include_destroyed: false,
    })
  } catch (e) {
    ui.error(e)
  } finally {
    loadingParents.value = false
  }
}

onMounted(() => {
  void catalog.ensure()
  void refs.ensure()
  void loadParents()
})
watch(() => props.templateId, loadParents)

interface Choice {
  title: string
  value: unknown
  subtitle?: string
}

/** Every value this type can take (before a list narrows it). */
const typeChoices = computed<Choice[]>(() => {
  switch (ft.value) {
    case 'industry':
    case 'project':
    case 'team':
      return catalog
        .byCategory(ft.value)
        .filter((o) => o.active)
        .map((o) => ({ title: o.value, value: o.id }))
    case 'managers':
      return refs.managers.map((u) => ({ title: u.full_name, value: u.id, subtitle: u.email }))
    case 'responsible':
      return refs.users.map((u) => ({ title: u.full_name, value: u.id, subtitle: u.email }))
    case 'location':
      return [...refs.locations]
        .sort((a, b) => Number(b.is_desiccator) - Number(a.is_desiccator))
        .map((l) => ({
          title: l.name,
          value: l.id,
          subtitle: l.is_desiccator ? t('fieldInput.desiccator') : l.building ?? undefined,
        }))
    case 'parent':
      return parentItems.value.map((i) => ({
        title: `${i.name} · ${i.serial}`,
        value: i.id,
        subtitle: i.location_name ?? undefined,
      }))
    case 'status':
      return ITEM_STATES.map((s) => ({ title: STATE_LABELS[s], value: s }))
    case 'letter':
      return LETTERS.map((l) => ({ title: l, value: l }))
    case 'boolean':
      return [
        { title: t('common.yes'), value: true },
        { title: t('common.no'), value: false },
      ]
    case 'enum':
      return ((props.field.config.options ?? []) as string[]).map((o) => ({ title: o, value: o }))
    default:
      return []
  }
})

/** The template's list, labelled. */
const listChoices = computed<Choice[]>(() => {
  const options = (props.field.config.options ?? []) as unknown[]
  const labels = props.field.options_display ?? []
  return options.map((o, i) => {
    const known = typeChoices.value.find((c) => c.value === o)
    return { title: labels[i] ?? known?.title ?? String(o), value: o }
  })
})

const multiple = computed(() => isOptions.value || ft.value === 'managers')

// Types picked from a list of known values (as opposed to typed in).
const PICKED: FieldType[] = [
  'industry', 'project', 'team', 'managers', 'responsible', 'location', 'parent', 'status',
  'letter', 'enum',
]
const picked = computed(() => fromList.value || PICKED.includes(ft.value))

// ── validation (mirrors the server, so mistakes show before the round-trip) ──
const pattern = computed(() => props.field.config.pattern ?? null)
const minLength = computed(() => props.field.config.min_length ?? 8)

const rules = computed(() => {
  if (isOptions.value) return []
  const out: ((v: unknown) => true | string)[] = []
  const empty = (v: unknown) => v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length)
  if (props.field.required) out.push((v) => !empty(v) || t('common.required'))
  if (ft.value === 'description') {
    out.push((v) => empty(v) || String(v).replace(/\s/g, '').length >= minLength.value
      || t('fieldInput.minChars', { n: minLength.value }))
  }
  if (ft.value === 'link') {
    out.push((v) => empty(v) || /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/\S+$/.test(String(v)) || t('fieldInput.badLink'))
  }
  if (pattern.value && !fromList.value) {
    const p = pattern.value
    out.push((v) => empty(v) || applyPattern(p, String(v)) !== null || t('fieldInput.badPattern', { p }))
  }
  if (ft.value === 'quantity') out.push((v) => empty(v) || Number(v) >= 1 || t('fieldInput.minOne'))
  if (ft.value === 'integer') out.push((v) => empty(v) || Number.isInteger(Number(v)) || t('fieldInput.wholeNumber'))
  return out
})

function onPatternBlur() {
  if (!pattern.value || typeof value.value !== 'string') return
  const formatted = applyPattern(pattern.value, value.value)
  if (formatted) value.value = formatted
}

const numberValue = computed({
  get: () => (value.value === null || value.value === undefined ? '' : String(value.value)),
  set: (v: string) => {
    if (v === '' || v === null) value.value = null
    else value.value = ft.value === 'decimal' ? Number(v) : Math.trunc(Number(v))
  },
})

// ── files: uploaded (staged) as soon as they are picked; the value is ids ──
const uploading = ref(false)
const knownFiles = ref<DocumentOut[]>([])
watch(
  () => props.files,
  (f) => {
    const ids = new Set(knownFiles.value.map((d) => d.id))
    for (const d of f ?? []) if (!ids.has(d.id)) knownFiles.value.push(d)
  },
  { immediate: true },
)
const attached = computed(() => {
  const ids = (value.value as number[] | null) ?? []
  return ids.map((id) => knownFiles.value.find((d) => d.id === id) ?? ({ id, name: `#${id}` } as DocumentOut))
})

async function onPickFiles(picked: File | File[] | null) {
  const list = Array.isArray(picked) ? picked : picked ? [picked] : []
  if (!list.length) return
  uploading.value = true
  try {
    const ids = [...(((value.value as number[] | null) ?? []))]
    for (const f of list) {
      const doc = await documentsApi.stage(f)
      knownFiles.value.push(doc)
      ids.push(doc.id)
    }
    value.value = ids
  } catch (e) {
    ui.error(e)
  } finally {
    uploading.value = false
  }
}

function removeFile(id: number) {
  value.value = ((value.value as number[] | null) ?? []).filter((x) => x !== id)
}
</script>

<template>
  <div class="field-input">
    <!-- files -->
    <template v-if="ft === 'files' && !isOptions">
      <v-file-input
        :label="label"
        :prepend-inner-icon="icon"
        prepend-icon=""
        multiple
        chips
        :loading="uploading"
        :disabled="disabled"
        :model-value="[]"
        :error-messages="errorMessages"
        :hint="$t('fieldInput.filesHint')"
        persistent-hint
        @update:model-value="onPickFiles"
      />
      <div v-if="attached.length" class="d-flex flex-wrap gap-2 mt-1 mb-2">
        <v-chip
          v-for="d in attached"
          :key="d.id"
          size="small"
          prepend-icon="mdi-paperclip"
          :closable="!disabled"
          @click:close="removeFile(d.id)"
        >
          <bdi>{{ d.name }}</bdi>
          <span v-if="d.size_bytes" class="text-medium-emphasis ms-1">{{ formatBytes(d.size_bytes) }}</span>
        </v-chip>
      </div>
    </template>

    <!-- picked from known values (or from the template's list) -->
    <v-autocomplete
      v-else-if="picked || (isOptions && typeChoices.length)"
      v-model="value"
      :label="label"
      :items="fromList ? listChoices : typeChoices"
      item-title="title"
      item-value="value"
      :multiple="multiple"
      :chips="multiple"
      :closable-chips="multiple"
      :clearable="!field.required || isOptions"
      :prepend-inner-icon="icon"
      :rules="rules"
      :disabled="disabled"
      :loading="loadingParents"
      :error-messages="errorMessages"
      :hint="ft === 'parent' ? $t('fieldInput.parentHint') : undefined"
      :persistent-hint="ft === 'parent'"
      :no-data-text="$t('fieldInput.noOptions')"
    >
      <template #item="{ props: itemProps, item }">
        <v-list-item v-bind="itemProps" :subtitle="(item.raw as Choice).subtitle" />
      </template>
    </v-autocomplete>

    <!-- a list of typed-in values (options of a text/number field) -->
    <v-combobox
      v-else-if="isOptions"
      v-model="value"
      :label="label"
      multiple
      chips
      closable-chips
      :prepend-inner-icon="icon"
      :hint="$t('fieldInput.optionsHint')"
      persistent-hint
      :disabled="disabled"
    />

    <v-switch
      v-else-if="ft === 'boolean'"
      v-model="value"
      :label="label"
      color="primary"
      :true-value="true"
      :false-value="false"
      :disabled="disabled"
      hide-details="auto"
      inset
    />

    <v-textarea
      v-else-if="ft === 'text' || ft === 'description'"
      v-model="value"
      :label="label"
      :prepend-inner-icon="icon"
      rows="2"
      auto-grow
      :rules="rules"
      :disabled="disabled"
      :error-messages="errorMessages"
      :hint="ft === 'description' ? $t('fieldInput.minChars', { n: minLength }) : undefined"
    />

    <v-text-field
      v-else-if="ft === 'integer' || ft === 'decimal' || ft === 'quantity'"
      v-model="numberValue"
      :label="label"
      type="number"
      :step="ft === 'decimal' ? 'any' : 1"
      :min="ft === 'quantity' ? 1 : undefined"
      :prepend-inner-icon="icon"
      :rules="rules"
      :disabled="disabled"
      :error-messages="errorMessages"
    />

    <!-- Not <input type="date">: its placeholder and format follow the
         browser's language, not the app's. -->
    <v-menu
      v-else-if="ft === 'date'"
      v-model="dateMenu"
      :close-on-content-click="false"
      :disabled="disabled"
      location="bottom start"
    >
      <template #activator="{ props: menu }">
        <v-text-field
          v-bind="menu"
          :model-value="value ? formatDate(String(value)) : ''"
          :label="label"
          :placeholder="$t('fieldInput.datePlaceholder')"
          :prepend-inner-icon="icon"
          append-inner-icon="mdi-calendar"
          readonly
          :clearable="!disabled"
          :rules="rules"
          :disabled="disabled"
          :error-messages="errorMessages"
          @click:clear="value = null"
        />
      </template>
      <v-date-picker
        :model-value="value ? parseDay(String(value)) : null"
        show-adjacent-months
        @update:model-value="(d: unknown) => pickDate(d)"
      />
    </v-menu>

    <v-text-field
      v-else
      v-model="value"
      :label="label"
      :prepend-inner-icon="icon"
      :rules="rules"
      :disabled="disabled"
      :error-messages="errorMessages"
      :placeholder="pattern ? pattern : undefined"
      :hint="pattern ? $t('fieldInput.patternHint', { p: pattern }) : undefined"
      :persistent-hint="!!pattern"
      @blur="onPatternBlur"
    />
  </div>
</template>
