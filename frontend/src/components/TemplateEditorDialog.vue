<script setup lang="ts">
// Create, edit or duplicate a template: its identity (type, name, card type,
// serial prefix), which templates may sit inside it (and how many of each),
// and its fields — typed in, or loaded from the catalog's field groups.
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { fieldGroupsApi, templatesApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import { stripIsolates } from '@/utils/bidi'
import FieldListEditor from '@/components/FieldListEditor.vue'
import FieldGroupPicker from '@/components/FieldGroupPicker.vue'
import { CARD_TYPES, CARD_TYPE_LABELS, ITEM_TYPES, SYSTEM_FIELD_TYPES, TYPE_LABELS, isQuantityTracked } from '@/constants'
import { type FieldRow, cleanFields, rowsFromGroup, rowsFromTemplate } from '@/lib/fieldRows'
import type {
  CardType,
  FieldGroupOut,
  ItemType,
  TemplateChildIn,
  TemplateCreate,
  TemplateOut,
  TemplateSummary,
} from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  template?: TemplateOut | null
  /** Start a new template as a copy of this one (everything stays editable). */
  duplicateFrom?: TemplateOut | null
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
const duplicating = computed(() => !editing.value && !!props.duplicateFrom)

const form = reactive<{
  type: ItemType
  name: string
  card_type: CardType | null
  serial_prefix: string
  description: string
  children: TemplateChildIn[]
  fields: FieldRow[]
}>({
  type: 'card',
  name: '',
  card_type: 'house',
  serial_prefix: '',
  description: '',
  children: [],
  fields: [],
})

const allTemplates = ref<TemplateSummary[]>([])
const formRef = ref()
const saving = ref(false)

async function hydrate() {
  const tpl = props.template ?? props.duplicateFrom ?? null
  const copy = duplicating.value
  Object.assign(form, {
    type: tpl?.type ?? props.type ?? 'card',
    name: tpl ? (copy ? stripIsolates(t('tplEditor.copyName', { name: tpl.name })) : tpl.name) : '',
    card_type: tpl ? tpl.card_type : (props.type ?? 'card') === 'card' ? 'house' : null,
    // A prefix is unique per type, so a copy needs its own.
    serial_prefix: copy ? '' : (tpl?.serial_prefix ?? ''),
    description: tpl?.description ?? '',
    children: (tpl?.children ?? []).map((c) => ({
      template_id: c.template.id,
      min_count: c.min_count,
      max_count: c.max_count,
    })),
    fields: rowsFromTemplate(tpl?.fields ?? [], copy),
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
const templateName = (id: number) => allTemplates.value.find((x) => x.id === id)?.name ?? `#${id}`

// The chips pick the templates; each keeps its limits while it stays picked.
const childIds = computed({
  get: () => form.children.map((c) => c.template_id),
  set: (ids: number[]) => {
    const have = new Map(form.children.map((c) => [c.template_id, c]))
    form.children = ids.map((id) => have.get(id) ?? { template_id: id, min_count: 0, max_count: null })
  },
})

function setMin(c: TemplateChildIn, v: string) {
  c.min_count = Math.max(0, Math.floor(Number(v) || 0))
}
function setMax(c: TemplateChildIn, v: string) {
  const n = Math.floor(Number(v))
  c.max_count = v === '' || v == null || !Number.isFinite(n) || n < 1 ? null : n
}
const limitError = (c: TemplateChildIn) =>
  c.max_count != null && c.max_count < c.min_count ? t('tplEditor.maxBelowMin') : ''

// ── field groups ──
const pickerOpen = ref(false)

function fits(row: FieldRow, taken: Set<string>): boolean {
  if (taken.has(row.label.trim().toLowerCase())) return false
  const ft = row.field_type
  if (SYSTEM_FIELD_TYPES.includes(ft) && form.fields.some((f) => f.field_type === ft)) return false
  if (ft === 'quantity') return isCard.value && isQuantityTracked(form.card_type)
  if (ft === 'parent') return form.type !== 'setup'
  return true
}

function loadGroups(groups: FieldGroupOut[]) {
  let added = 0
  const skipped: string[] = []
  for (const g of groups) {
    for (const row of rowsFromGroup(g.fields)) {
      const taken = new Set(form.fields.map((f) => f.label.trim().toLowerCase()))
      if (fits(row, taken)) {
        form.fields.push(row)
        added++
      } else {
        skipped.push(row.label)
      }
    }
  }
  if (skipped.length) ui.warning(t('fieldGroups.loadedSkipped', { n: added, skipped: skipped.join(', ') }))
  else ui.success(t('fieldGroups.loaded', { n: added }))
}

const saveGroupOpen = ref(false)
const groupForm = reactive({ name: '', description: '' })
const savingGroup = ref(false)

function openSaveGroup() {
  if (!form.fields.length) return
  groupForm.name = form.name.trim() ? stripIsolates(t('fieldGroups.defaultName', { name: form.name.trim() })) : ''
  groupForm.description = ''
  saveGroupOpen.value = true
}

async function saveGroup() {
  if (!groupForm.name.trim()) return
  savingGroup.value = true
  try {
    await fieldGroupsApi.create({
      name: groupForm.name.trim(),
      description: groupForm.description.trim() || null,
      fields: cleanFields(form.fields, false).map(({ copy_files_from: _c, ...f }) => f),
    })
    ui.success(t('fieldGroups.saved', { name: groupForm.name.trim() }))
    saveGroupOpen.value = false
  } catch (e) {
    ui.error(e)
  } finally {
    savingGroup.value = false
  }
}

// ── submit ──
const prefixRules = [
  (v: string) => /^[A-Za-z]{3}$/.test(v?.trim() ?? '') || t('tplEditor.prefixRule'),
]
const nameRules = [(v: string) => !!v?.trim() || t('common.required')]

async function submit() {
  const res = await formRef.value?.validate()
  if (res && !res.valid) return
  if (form.fields.some((f) => !f.label.trim())) {
    ui.warning(t('tplEditor.fieldNameRequired'))
    return
  }
  if (form.children.some((c) => limitError(c))) {
    ui.warning(t('tplEditor.maxBelowMin'))
    return
  }
  const payload: TemplateCreate = {
    type: form.type,
    name: form.name.trim(),
    card_type: isCard.value ? form.card_type : null,
    serial_prefix: form.serial_prefix.trim().toUpperCase(),
    description: form.description.trim() || null,
    fields: cleanFields(form.fields),
    children: childTypes.value.length ? form.children : [],
  }
  saving.value = true
  try {
    if (editing.value) {
      const { type: _type, ...update } = payload
      emit('submit', isCard.value ? update : { ...update, card_type: undefined })
    } else {
      emit('submit', duplicating.value ? { ...payload, source_template_id: props.duplicateFrom!.id } : payload)
    }
  } finally {
    saving.value = false
  }
}

const title = computed(() =>
  editing.value
    ? t('tplEditor.editTitle', { name: props.template?.name })
    : duplicating.value
      ? t('tplEditor.duplicateTitle', { name: props.duplicateFrom?.name })
      : t('tplEditor.newTitle', { type: TYPE_LABELS[form.type] }),
)
</script>

<template>
  <v-dialog v-model="open" max-width="980" scrollable>
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon :icon="duplicating ? 'mdi-content-copy' : 'mdi-shape-square-plus'" color="primary" />
        <span class="text-h6">{{ title }}</span>
      </v-card-title>
      <v-divider />

      <v-card-text class="pa-4" style="max-height: 74vh">
        <v-alert v-if="duplicating" type="info" variant="tonal" density="compact" class="mb-3">
          {{ $t('tplEditor.duplicateHint') }}
        </v-alert>
        <v-form ref="formRef" @submit.prevent="submit">
          <!-- identity -->
          <v-row dense>
            <v-col cols="12" sm="4">
              <v-select
                v-model="form.type"
                :label="$t('fields.type')"
                :items="ITEM_TYPES.map((ty) => ({ title: TYPE_LABELS[ty], value: ty }))"
                :disabled="editing || duplicating"
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
                dir="ltr"
                :placeholder="$t('tplEditor.prefixPlaceholder')"
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
                v-model="childIds"
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
            <v-col v-if="childTypes.length && form.children.length" cols="12">
              <div class="text-overline text-medium-emphasis">{{ $t('tplEditor.limitsTitle') }}</div>
              <div class="text-caption text-medium-emphasis mb-2">{{ $t('tplEditor.limitsHint') }}</div>
              <div v-for="c in form.children" :key="c.template_id" class="limit-row d-flex align-center flex-wrap gap-3 mb-2">
                <v-icon icon="mdi-puzzle-outline" size="18" class="text-medium-emphasis" />
                <bdi class="font-weight-medium limit-name">{{ templateName(c.template_id) }}</bdi>
                <v-text-field
                  :model-value="c.min_count"
                  :label="$t('tplEditor.minCount')"
                  type="number"
                  min="0"
                  density="compact"
                  hide-details
                  class="limit-input"
                  @update:model-value="(v: string) => setMin(c, v)"
                />
                <v-text-field
                  :model-value="c.max_count ?? ''"
                  :label="$t('tplEditor.maxCount')"
                  :placeholder="$t('tplEditor.noLimit')"
                  persistent-placeholder
                  type="number"
                  min="1"
                  density="compact"
                  :error-messages="limitError(c)"
                  hide-details="auto"
                  class="limit-input"
                  @update:model-value="(v: string) => setMax(c, v)"
                />
              </div>
            </v-col>
          </v-row>

          <FieldListEditor v-model="form.fields" :item-type="form.type" :card-type="form.card_type">
            <template #actions>
              <v-btn size="small" variant="text" prepend-icon="mdi-playlist-plus" @click="pickerOpen = true">
                {{ $t('fieldGroups.load') }}
              </v-btn>
              <v-btn
                v-if="direct"
                size="small"
                variant="text"
                prepend-icon="mdi-content-save-outline"
                :disabled="!form.fields.length"
                @click="openSaveGroup"
              >
                {{ $t('fieldGroups.saveAs') }}
              </v-btn>
            </template>
          </FieldListEditor>
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

    <FieldGroupPicker v-model="pickerOpen" @load="loadGroups" />

    <v-dialog v-model="saveGroupOpen" max-width="460">
      <v-card rounded="lg">
        <v-card-title class="pa-4">{{ $t('fieldGroups.saveAs') }}</v-card-title>
        <v-card-text>
          <div class="text-caption text-medium-emphasis mb-3">
            {{ $t('fieldGroups.saveHint', { n: form.fields.length }) }}
          </div>
          <v-text-field v-model="groupForm.name" :label="$t('fieldGroups.name')" autofocus />
          <v-text-field v-model="groupForm.description" :label="$t('fields.description')" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="saveGroupOpen = false">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="savingGroup" :disabled="!groupForm.name.trim()" @click="saveGroup">
            {{ $t('common.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-dialog>
</template>

<style scoped>
.limit-row {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  padding: 8px 12px;
}
.limit-name {
  min-width: 180px;
}
.limit-input {
  max-width: 140px;
}
</style>
