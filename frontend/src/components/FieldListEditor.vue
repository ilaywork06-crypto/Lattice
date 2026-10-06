<script setup lang="ts">
// The editable list of field definitions shared by the template editor and the
// field-group editor (Catalog → Field groups).
//
// Field colours follow the spec's legend:
//   white  — set on the template (shared by every item; "fixed")
//   white ▾ — a list defined on the template; each item picks (first = default)
//   grey   — filled in when an item is created
//   *      — required
import { computed } from 'vue'
import FieldInput from '@/components/FieldInput.vue'
import {
  FIELD_MODE_LABELS,
  FIELD_TYPE_GROUPS,
  FIELD_TYPE_ICONS,
  FIELD_TYPE_LABELS,
  PER_UNIT_FIELD_TYPES,
  SYSTEM_FIELD_TYPES,
  isQuantityTracked,
} from '@/constants'
import type { CardType, FieldConfig, FieldMode, FieldType, ItemType } from '@/api/types'
import { type FieldRow, newFieldRow } from '@/lib/fieldRows'

const props = defineProps<{
  /** The template kind the fields are for; null = any (a field group). */
  itemType: ItemType | null
  cardType?: CardType | null
}>()

const rows = defineModel<FieldRow[]>({ required: true })

const usedSystemTypes = computed(
  () => new Set(rows.value.map((f) => f.field_type).filter((ft) => SYSTEM_FIELD_TYPES.includes(ft))),
)

function typeAllowed(ft: FieldType): boolean {
  if (usedSystemTypes.value.has(ft)) return false
  if (props.itemType === null) return true
  if (ft === 'quantity') return props.itemType === 'card' && isQuantityTracked(props.cardType ?? null)
  if (ft === 'parent') return props.itemType !== 'setup'
  return true
}

function addField(ft: FieldType) {
  rows.value.push(newFieldRow(ft, FIELD_TYPE_LABELS[ft]))
}

function removeField(i: number) {
  rows.value.splice(i, 1)
}

function moveField(i: number, delta: number) {
  const j = i + delta
  if (j < 0 || j >= rows.value.length) return
  const [row] = rows.value.splice(i, 1)
  rows.value.splice(j, 0, row)
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
</script>

<template>
  <div>
    <!-- legend -->
    <div class="d-flex flex-wrap align-center gap-4 mt-4 mb-2 text-caption">
      <span class="d-flex align-center gap-1"><span class="chip-white" /> {{ $t('tplEditor.legendWhite') }}</span>
      <span class="d-flex align-center gap-1"><span class="chip-white"><v-icon icon="mdi-menu-down" size="14" /></span> {{ $t('tplEditor.legendList') }}</span>
      <span class="d-flex align-center gap-1"><span class="chip-grey" /> {{ $t('tplEditor.legendGrey') }}</span>
      <span class="d-flex align-center gap-1"><strong class="text-error">*</strong> {{ $t('tplEditor.legendRequired') }}</span>
    </div>

    <div class="d-flex align-center flex-wrap gap-2 mb-2">
      <div class="text-overline text-medium-emphasis">
        {{ $t('tplEditor.fields', { n: rows.length }) }}
      </div>
      <v-spacer />
      <slot name="actions" />
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
      v-if="!rows.length"
      type="info"
      variant="tonal"
      density="compact"
      icon="mdi-information-outline"
    >
      {{ $t('tplEditor.noFields') }}
    </v-alert>

    <div
      v-for="(row, i) in rows"
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
        <v-btn icon="mdi-arrow-up" size="x-small" variant="text" :aria-label="$t('tplEditor.moveUp')" :disabled="i === 0" @click="moveField(i, -1)" />
        <v-btn
          icon="mdi-arrow-down"
          size="x-small"
          variant="text"
          :aria-label="$t('tplEditor.moveDown')"
          :disabled="i === rows.length - 1"
          @click="moveField(i, 1)"
        />
        <v-btn
          :icon="row.expanded ? 'mdi-chevron-up' : 'mdi-cog-outline'"
          size="x-small"
          variant="text"
          :aria-label="$t('tplEditor.fieldSettings')"
          @click="row.expanded = !row.expanded"
        />
        <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error" :aria-label="$t('common.delete')" @click="removeField(i)" />
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
                :placeholder="$t('tplEditor.patternPlaceholder')"
                :hint="$t('tplEditor.patternHint')"
                persistent-hint
                dir="ltr"
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
                {{ row.copy_files_from ? $t('tplEditor.filesCopiedHint') : $t('tplEditor.templateFilesHint') }}
              </v-alert>
            </v-col>
          </v-row>
        </div>
      </v-expand-transition>
    </div>
  </div>
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
