<script setup lang="ts">
// Create or edit a template: its identity (type, name, card type, serial
// prefix), which templates may sit inside it, and its fields.
//
// Field colours follow the spec's legend:
//   white  — set on the template (shared by every item; "fixed")
//   white ▾ — a list defined on the template; each item picks (first = default)
//   grey   — filled in when an item is created
//   *      — required
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { templatesApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import FieldInput from '@/components/FieldInput.vue'
import {
  CARD_TYPES,
  CARD_TYPE_LABELS,
  FIELD_MODE_LABELS,
  FIELD_TYPE_GROUPS,
  FIELD_TYPE_ICONS,
  FIELD_TYPE_LABELS,
  ITEM_TYPES,
  PER_UNIT_FIELD_TYPES,
  SYSTEM_FIELD_TYPES,
  TYPE_LABELS,
  isQuantityTracked,
} from '@/constants'
import type {
  CardType,
  FieldConfig,
  FieldMode,
  FieldType,
  ItemType,
  TemplateCreate,
  TemplateFieldIn,
  TemplateOut,
  TemplateSummary,
} from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  template?: TemplateOut | null
  type?: ItemType | null
  /** Managers save directly; editors submit a proposal. */
  direct: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  /** create → TemplateCreate; edit → the changed TemplateUpdate fields */
  submit: [payload: TemplateCreate | Partial<TemplateCreate>]
}>()

const { t } = useI18n({ useScope: 'global' })
const ui = useUiStore()

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
const editing = computed(() => !!props.template)

interface FieldRow extends TemplateFieldIn {
  uid: number
  expanded: boolean
}

const form = reactive<{
  type: ItemType
  name: string
  card_type: CardType | null
  serial_prefix: string
  description: string
  child_template_ids: number[]
  fields: FieldRow[]
}>({
  type: 'card',
  name: '',
  card_type: 'house',
  serial_prefix: '',
  description: '',
  child_template_ids: [],
  fields: [],
})

let uid = 0
const allTemplates = ref<TemplateSummary[]>([])
const formRef = ref()
const saving = ref(false)

async function hydrate() {
  const tpl = props.template
  Object.assign(form, {
    type: tpl?.type ?? props.type ?? 'card',
    name: tpl?.name ?? '',
    card_type: tpl ? tpl.card_type : (props.type ?? 'card') === 'card' ? 'house' : null,
    serial_prefix: tpl?.serial_prefix ?? '',
    description: tpl?.description ?? '',
    child_template_ids: tpl?.child_template_ids ?? [],
    fields: (tpl?.fields ?? []).map((f) => ({
      uid: ++uid,
      expanded: false,
      id: f.id,
      key: f.key,
      label: f.label,
      field_type: f.field_type,
      mode: f.mode,
      required: f.required,
      config: { ...f.config },
      fixed_value: f.fixed_value,
    })),
  })
  try {
    allTemplates.value = await templatesApi.list()
  } catch (e) {
    ui.error(e)
  }
}

watch(open, (v) => {
  if (v) void hydrate()
})

const isCard = computed(() => form.type === 'card')
const childTypes = computed<ItemType[]>(() =>
  form.type === 'setup' ? ['assembly', 'card'] : form.type === 'assembly' ? ['card'] : [],
)
const childChoices = computed(() =>
  allTemplates.value
    .filter((tp) => childTypes.value.includes(tp.type) && tp.id !== props.template?.id)
    .map((tp) => ({
      title: tp.name,
      value: tp.id,
      subtitle: `${TYPE_LABELS[tp.type]} · ${tp.serial_prefix}`,
    })),
)

// ── field list ──
const usedSystemTypes = computed(
  () => new Set(form.fields.map((f) => f.field_type).filter((ft) => SYSTEM_FIELD_TYPES.includes(ft))),
)

function typeAllowed(ft: FieldType): boolean {
  if (usedSystemTypes.value.has(ft)) return false
  if (ft === 'quantity') return isCard.value && isQuantityTracked(form.card_type)
  if (ft === 'parent') return form.type !== 'setup'
  return true
}

function addField(ft: FieldType) {
  const row: FieldRow = {
    uid: ++uid,
    expanded: true,
    id: null,
    key: null,
    label: FIELD_TYPE_LABELS[ft],
    field_type: ft,
    mode: 'item',
    required: false,
    config: ft === 'description' ? { min_length: 8 } : {},
    fixed_value: null,
  }
  form.fields.push(row)
}

function removeField(i: number) {
  form.fields.splice(i, 1)
}

function moveField(i: number, delta: number) {
  const j = i + delta
  if (j < 0 || j >= form.fields.length) return
  const [row] = form.fields.splice(i, 1)
  form.fields.splice(j, 0, row)
}

function modesFor(ft: FieldType): FieldMode[] {
  if (PER_UNIT_FIELD_TYPES.includes(ft)) return ft === 'parent' ? ['item'] : ['choice', 'item']
  if (ft === 'files') return ['fixed', 'item']
  return ['fixed', 'choice', 'item']
}

function setMode(row: FieldRow, mode: FieldMode) {
  row.mode = mode
  if (mode !== 'fixed') row.fixed_value = null
  if (mode !== 'choice' && row.field_type !== 'enum') {
    const { options: _drop, ...rest } = row.config as FieldConfig
    row.config = rest
  }
}

const MODE_ICONS: Record<FieldMode, string> = {
  fixed: 'mdi-square-outline',
  choice: 'mdi-menu-down',
  item: 'mdi-square',
}

const enumOptions = (row: FieldRow) =>
  computed({
    get: () => ((row.config.options ?? []) as string[]),
    set: (v: string[]) => {
      row.config = { ...row.config, options: v }
    },
  })

function optionsModel(row: FieldRow) {
  return computed({
    get: () => (row.config.options ?? []) as unknown[],
    set: (v: unknown) => {
      row.config = { ...row.config, options: (v as unknown[]) ?? [] }
    },
  })
}

// ── submit ──
const prefixRules = [
  (v: string) => /^[A-Za-z]{3}$/.test(v?.trim() ?? '') || t('tplEditor.prefixRule'),
]
const nameRules = [(v: string) => !!v?.trim() || t('common.required')]

function cleanFields(): TemplateFieldIn[] {
  return form.fields.map((f) => ({
    id: f.id ?? null,
    key: f.key ?? null,
    label: f.label.trim(),
    field_type: f.field_type,
    mode: f.mode,
    required: f.required,
    config: f.config,
    fixed_value: f.mode === 'fixed' ? f.fixed_value : null,
  }))
}

async function submit() {
  const res = await formRef.value?.validate()
  if (res && !res.valid) return
  if (form.fields.some((f) => !f.label.trim())) {
    ui.warning(t('tplEditor.fieldNameRequired'))
    return
  }
  const payload: TemplateCreate = {
    type: form.type,
    name: form.name.trim(),
    card_type: isCard.value ? form.card_type : null,
    serial_prefix: form.serial_prefix.trim().toUpperCase(),
    description: form.description.trim() || null,
    fields: cleanFields(),
    child_template_ids: form.child_template_ids,
  }
  saving.value = true
  try {
    if (editing.value) {
      const { type: _type, ...update } = payload
      emit('submit', isCard.value ? update : { ...update, card_type: undefined })
    } else {
      emit('submit', payload)
    }
  } finally {
    saving.value = false
  }
}

const title = computed(() =>
  editing.value
    ? t('tplEditor.editTitle', { name: props.template?.name })
    : t('tplEditor.newTitle', { type: TYPE_LABELS[form.type] }),
)
</script>

<template>
  <v-dialog v-model="open" max-width="980" scrollable>
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon icon="mdi-shape-square-plus" color="primary" />
        <span class="text-h6">{{ title }}</span>
      </v-card-title>
      <v-divider />

      <v-card-text class="pa-4" style="max-height: 74vh">
        <v-form ref="formRef" @submit.prevent="submit">
          <!-- identity -->
          <v-row dense>
            <v-col cols="12" sm="4">
              <v-select
                v-model="form.type"
                :label="$t('fields.type')"
                :items="ITEM_TYPES.map((ty) => ({ title: TYPE_LABELS[ty], value: ty }))"
                :disabled="editing"
                @update:model-value="(v: ItemType) => (form.card_type = v === 'card' ? 'house' : null)"
              />
            </v-col>
            <v-col cols="12" sm="5">
              <v-text-field v-model="form.name" :label="$t('tplEditor.name')" :rules="nameRules" />
            </v-col>
            <v-col cols="12" sm="3">
              <v-text-field
                v-model="form.serial_prefix"
                :label="$t('tplEditor.prefix')"
                :rules="prefixRules"
                maxlength="3"
                :hint="$t('tplEditor.prefixHint', { example: `${form.type === 'card' ? 'C' : form.type === 'assembly' ? 'A' : 'S'}-${(form.serial_prefix || 'XXX').toUpperCase()}-001` })"
                persistent-hint
                @update:model-value="(v: string) => (form.serial_prefix = (v || '').toUpperCase())"
              />
            </v-col>
            <v-col v-if="isCard" cols="12" sm="4">
              <v-select
                v-model="form.card_type"
                :label="$t('fields.cardType')"
                :items="CARD_TYPES.map((c) => ({ title: CARD_TYPE_LABELS[c], value: c }))"
              />
            </v-col>
            <v-col cols="12" :sm="isCard ? 8 : 12">
              <v-text-field v-model="form.description" :label="$t('fields.description')" />
            </v-col>
            <v-col v-if="childTypes.length" cols="12">
              <v-autocomplete
                v-model="form.child_template_ids"
                :label="form.type === 'setup' ? $t('tplEditor.childrenSetup') : $t('tplEditor.childrenAssembly')"
                :items="childChoices"
                item-title="title"
                item-value="value"
                multiple
                chips
                closable-chips
                :hint="$t('tplEditor.childrenHint')"
                persistent-hint
              >
                <template #item="{ props: itemProps, item }">
                  <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
                </template>
              </v-autocomplete>
            </v-col>
          </v-row>

          <!-- legend -->
          <div class="legend d-flex flex-wrap align-center gap-4 mt-4 mb-2 text-caption">
            <span class="d-flex align-center gap-1"><span class="chip-white" /> {{ $t('tplEditor.legendWhite') }}</span>
            <span class="d-flex align-center gap-1"><span class="chip-white"><v-icon icon="mdi-menu-down" size="14" /></span> {{ $t('tplEditor.legendList') }}</span>
            <span class="d-flex align-center gap-1"><span class="chip-grey" /> {{ $t('tplEditor.legendGrey') }}</span>
            <span class="d-flex align-center gap-1"><strong class="text-error">*</strong> {{ $t('tplEditor.legendRequired') }}</span>
          </div>

          <!-- fields -->
          <div class="d-flex align-center mb-2">
            <div class="text-overline text-medium-emphasis">
              {{ $t('tplEditor.fields', { n: form.fields.length }) }}
            </div>
            <v-spacer />
            <v-menu location="bottom end" max-height="420">
              <template #activator="{ props: menu }">
                <v-btn v-bind="menu" size="small" color="primary" variant="tonal" prepend-icon="mdi-plus">
                  {{ $t('tplEditor.addField') }}
                </v-btn>
              </template>
              <v-list density="compact" nav>
                <template v-for="g in FIELD_TYPE_GROUPS" :key="g.group">
                  <v-list-subheader>{{ $t('tplEditor.groups.' + g.group) }}</v-list-subheader>
                  <v-list-item
                    v-for="ft in g.types"
                    :key="ft"
                    :prepend-icon="FIELD_TYPE_ICONS[ft]"
                    :title="FIELD_TYPE_LABELS[ft]"
                    :disabled="!typeAllowed(ft)"
                    @click="addField(ft)"
                  />
                </template>
              </v-list>
            </v-menu>
          </div>

          <v-alert
            v-if="!form.fields.length"
            type="info"
            variant="tonal"
            density="compact"
            icon="mdi-information-outline"
          >
            {{ $t('tplEditor.noFields') }}
          </v-alert>

          <div
            v-for="(row, i) in form.fields"
            :key="row.uid"
            class="field-row mb-2"
            :class="row.mode === 'item' ? 'is-grey' : 'is-white'"
          >
            <div class="d-flex align-center gap-2 flex-wrap">
              <v-icon :icon="FIELD_TYPE_ICONS[row.field_type]" size="20" class="text-medium-emphasis" />
              <v-text-field
                v-model="row.label"
                :label="$t('tplEditor.fieldName')"
                density="compact"
                hide-details
                class="field-name"
              />
              <v-chip size="small" variant="tonal">{{ FIELD_TYPE_LABELS[row.field_type] }}</v-chip>
              <v-btn-toggle
                :model-value="row.mode"
                density="compact"
                variant="outlined"
                divided
                mandatory
                rounded="lg"
                @update:model-value="(m: FieldMode) => setMode(row, m)"
              >
                <v-btn
                  v-for="m in modesFor(row.field_type)"
                  :key="m"
                  :value="m"
                  size="small"
                  :prepend-icon="MODE_ICONS[m]"
                >
                  {{ FIELD_MODE_LABELS[m] }}
                </v-btn>
              </v-btn-toggle>
              <v-checkbox
                v-model="row.required"
                :label="$t('tplEditor.required')"
                density="compact"
                hide-details
                color="error"
              />
              <v-spacer />
              <v-btn icon="mdi-arrow-up" size="x-small" variant="text" :disabled="i === 0" @click="moveField(i, -1)" />
              <v-btn
                icon="mdi-arrow-down"
                size="x-small"
                variant="text"
                :disabled="i === form.fields.length - 1"
                @click="moveField(i, 1)"
              />
              <v-btn
                :icon="row.expanded ? 'mdi-chevron-up' : 'mdi-cog-outline'"
                size="x-small"
                variant="text"
                @click="row.expanded = !row.expanded"
              />
              <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error" @click="removeField(i)" />
            </div>

            <v-expand-transition>
              <div v-if="row.expanded" class="mt-3">
                <v-row dense>
                  <!-- the enum's own values -->
                  <v-col v-if="row.field_type === 'enum'" cols="12">
                    <v-combobox
                      v-model="enumOptions(row).value"
                      :label="$t('tplEditor.enumValues')"
                      multiple
                      chips
                      closable-chips
                      :hint="$t('tplEditor.enumHint')"
                      persistent-hint
                    />
                  </v-col>
                  <!-- a list field's allowed values -->
                  <v-col v-else-if="row.mode === 'choice'" cols="12">
                    <FieldInput
                      v-model="optionsModel(row).value"
                      :field="{ ...row, label: $t('tplEditor.listValues') }"
                      mode="options"
                    />
                    <div class="text-caption text-medium-emphasis mt-n2 mb-2">
                      {{ $t('tplEditor.listHint') }}
                    </div>
                  </v-col>
                  <!-- formats -->
                  <v-col v-if="row.field_type === 'string' || row.field_type === 'serial_string'" cols="12" sm="6">
                    <v-text-field
                      :model-value="row.config.pattern ?? ''"
                      :label="$t('tplEditor.pattern')"
                      placeholder="XX-#####"
                      :hint="$t('tplEditor.patternHint')"
                      persistent-hint
                      @update:model-value="(v: string) => (row.config = { ...row.config, pattern: v || undefined })"
                    />
                  </v-col>
                  <v-col v-if="row.field_type === 'description'" cols="12" sm="6">
                    <v-text-field
                      :model-value="row.config.min_length ?? 8"
                      :label="$t('tplEditor.minLength')"
                      type="number"
                      min="1"
                      @update:model-value="(v: string) => (row.config = { ...row.config, min_length: Number(v) || 8 })"
                    />
                  </v-col>
                  <!-- the template's value (white fields) -->
                  <v-col v-if="row.mode === 'fixed' && row.field_type !== 'files'" cols="12">
                    <FieldInput
                      v-model="row.fixed_value"
                      :field="{ ...row, label: $t('tplEditor.templateValue', { name: row.label }) }"
                    />
                  </v-col>
                  <v-col v-if="row.mode === 'fixed' && row.field_type === 'files'" cols="12">
                    <v-alert type="info" variant="tonal" density="compact">
                      {{ $t('tplEditor.templateFilesHint') }}
                    </v-alert>
                  </v-col>
                </v-row>
              </div>
            </v-expand-transition>
          </div>
        </v-form>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-3">
        <span v-if="editing" class="text-caption text-medium-emphasis ms-2">
          {{ $t('tplEditor.propagates') }}
        </span>
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ $t('common.cancel') }}</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="saving"
          :prepend-icon="direct ? 'mdi-content-save' : 'mdi-send'"
          @click="submit"
        >
          {{ direct ? $t('common.save') : $t('dlg.continueToProposal') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.field-row {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  padding: 10px 12px;
}
.field-row.is-white {
  background: rgb(var(--v-theme-surface));
}
.field-row.is-grey {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.field-name {
  max-width: 260px;
  min-width: 180px;
}
.chip-white,
.chip-grey {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 16px;
  border-radius: 4px;
  border: 1px solid rgba(var(--v-border-color), 0.4);
}
.chip-white {
  background: rgb(var(--v-theme-surface));
}
.chip-grey {
  background: rgba(var(--v-theme-on-surface), 0.12);
}
</style>
