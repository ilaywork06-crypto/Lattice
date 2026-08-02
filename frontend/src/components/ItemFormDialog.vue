<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { itemsApi, locationsApi, usersApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import { useCatalogStore } from '@/stores/catalog'
import {
  CARD_TYPES,
  CARD_TYPE_LABELS,
  isQuantityTracked,
  ITEM_STATES,
  STATE_LABELS,
  STORAGE_LABELS,
  STORAGE_STATUSES,
  TYPE_LABELS,
} from '@/constants'
import type {
  CardType,
  ItemCreate,
  ItemOut,
  ItemState,
  ItemType,
  ItemUpdate,
  LocationOut,
  StorageStatus,
  UserBrief,
} from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  mode: 'create' | 'edit'
  type?: ItemType
  item?: ItemOut | null
  // Pre-fill a *create* form (duplicate an item, or spin up from a template).
  prefill?: Partial<ItemCreate> | null
  // Creating a reusable template — hides all hierarchy fields.
  asTemplate?: boolean
  // manager submits directly; editor proposes. Controls the submit button label.
  direct: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: ItemCreate | ItemUpdate]
}>()

const ui = useUiStore()
const catalog = useCatalogStore()
const { t } = useI18n({ useScope: 'global' })

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const itemType = computed<ItemType>(() => props.type ?? props.item?.type ?? 'setup')
const isCard = computed(() => itemType.value === 'card')
// Only when creating a real (non-template) item can we wire up the hierarchy.
const showHierarchy = computed(() => props.mode === 'create' && !props.asTemplate)

// Which parent types this item may attach to (§8: a card can sit directly in a
// setup as well as an assembly).
const ALLOWED_PARENTS: Record<ItemType, ItemType[]> = {
  card: ['assembly', 'setup'],
  assembly: ['setup'],
  setup: [],
}
// Which existing items this item can adopt as children (§6/§8).
const CHILD_TYPES: Record<ItemType, ItemType[]> = {
  setup: ['assembly', 'card'],
  assembly: ['card'],
  card: [],
}
const allowedParents = computed(() => ALLOWED_PARENTS[itemType.value])
const childTypes = computed(() => CHILD_TYPES[itemType.value])

interface FormModel {
  name: string
  industry: string | null
  project: string | null
  team: string
  state: ItemState
  description: string
  dmz: string
  location_id: number | null
  parent_id: number | null
  card_type: CardType | null
  responsible: string
  lead: string
  production_date: string
  version: string
  serial: string
  quantity: number
  storage_status: StorageStatus | null
  manager_ids: number[]
  child_ids: number[]
  state_note: string
}

function emptyModel(): FormModel {
  return {
    name: '',
    industry: null,
    project: null,
    team: '',
    state: 'production',
    description: '',
    dmz: '',
    location_id: null,
    parent_id: null,
    card_type: null,
    responsible: '',
    lead: '',
    production_date: '',
    version: '',
    serial: '',
    quantity: 1,
    storage_status: null,
    manager_ids: [],
    child_ids: [],
    state_note: '',
  }
}

const form = reactive<FormModel>(emptyModel())

// The two kinds of card are filled in differently, and the form says so rather
// than letting the server reject the save: a commercial card is a quantity of
// interchangeable parts, everything else is one board with its own serial.
const byQuantity = computed(() => isCard.value && isQuantityTracked(form.card_type))
const bySerial = computed(() => isCard.value && !!form.card_type && !byQuantity.value)
const formRef = ref()
const valid = ref(false)
const saving = ref(false)

const locations = ref<LocationOut[]>([])
const managers = ref<UserBrief[]>([])
const parentOptions = ref<{ id: number; name: string; type: ItemType }[]>([])
const childOptions = ref<{ id: number; name: string; type: ItemType; parent_id: number | null }[]>([])
const loadingRefs = ref(false)

// Project/industry dropdowns from the admin catalog (preserving any legacy value).
const projectItems = computed(() => catalog.activeValues(catalog.projects, form.project))
const industryItems = computed(() => catalog.activeValues(catalog.industries, form.industry))

const parentSelectItems = computed(() =>
  parentOptions.value.map((p) => ({
    title: `${p.name} · ${TYPE_LABELS[p.type]}`,
    value: p.id,
  })),
)
const childSelectItems = computed(() =>
  childOptions.value.map((c) => ({
    title: c.parent_id
      ? `${c.name} · ${TYPE_LABELS[c.type]} (${t('itemForm.willMove')})`
      : `${c.name} · ${TYPE_LABELS[c.type]}`,
    value: c.id,
  })),
)

async function loadReferences() {
  loadingRefs.value = true
  try {
    const [locs, mgrs] = await Promise.all([
      locationsApi.list(),
      usersApi.managers(),
      catalog.ensure(),
    ])
    locations.value = locs
    managers.value = mgrs

    if (showHierarchy.value && allowedParents.value.length) {
      const lists = await Promise.all(
        allowedParents.value.map((ty) => itemsApi.list({ type: ty, limit: 500 })),
      )
      parentOptions.value = lists
        .flat()
        .filter((i) => i.id !== props.item?.id)
        .map((i) => ({ id: i.id, name: i.name, type: i.type }))
    } else {
      parentOptions.value = []
    }

    if (showHierarchy.value && childTypes.value.length) {
      const lists = await Promise.all(
        childTypes.value.map((ty) => itemsApi.list({ type: ty, limit: 500 })),
      )
      childOptions.value = lists
        .flat()
        .map((i) => ({ id: i.id, name: i.name, type: i.type, parent_id: i.parent_id }))
        // show unassigned first, then already-parented (which will be re-homed)
        .sort((a, b) => Number(!!a.parent_id) - Number(!!b.parent_id) || a.name.localeCompare(b.name))
    } else {
      childOptions.value = []
    }
  } catch (e) {
    ui.error(e)
  } finally {
    loadingRefs.value = false
  }
}

// Where the item's state stood when the dialog opened. A state change from the
// edit form goes through the same faulty-note rule as the dedicated dialog, so
// we need the original to know whether a note is owed.
const originalState = ref<ItemState | null>(null)

const stateChanged = computed(
  () => props.mode === 'edit' && originalState.value !== null && form.state !== originalState.value,
)
const stateNoteRequired = computed(
  () => stateChanged.value && (form.state === 'faulty' || originalState.value === 'faulty'),
)

function hydrate() {
  Object.assign(form, emptyModel())
  originalState.value = props.mode === 'edit' && props.item ? props.item.state : null
  if (props.mode === 'edit' && props.item) {
    const it = props.item
    Object.assign(form, {
      name: it.name,
      industry: it.industry ?? null,
      project: it.project ?? null,
      team: it.team ?? '',
      state: it.state,
      description: it.description ?? '',
      dmz: it.dmz ?? '',
      location_id: it.location_id ?? null,
      parent_id: it.parent_id ?? null,
      card_type: it.card_type ?? null,
      responsible: it.responsible ?? '',
      lead: it.lead ?? '',
      production_date: it.production_date ?? '',
      version: it.version ?? '',
      serial: it.serial ?? '',
      quantity: it.quantity ?? 1,
      storage_status: it.storage_status ?? null,
      manager_ids: it.managers.map((m) => m.id),
    })
  } else if (props.prefill) {
    // duplicate / from-template
    const p = props.prefill
    Object.assign(form, {
      name: p.name ?? '',
      industry: p.industry ?? null,
      project: p.project ?? null,
      team: p.team ?? '',
      state: p.state ?? 'production',
      description: p.description ?? '',
      dmz: p.dmz ?? '',
      location_id: p.location_id ?? null,
      card_type: p.card_type ?? (isCard.value ? 'company' : null),
      responsible: p.responsible ?? '',
      lead: p.lead ?? '',
      version: p.version ?? '',
      quantity: p.quantity ?? 1,
      storage_status: p.storage_status ?? (isCard.value && !props.asTemplate ? 'desiccator' : null),
      manager_ids: p.manager_ids ?? [],
    })
  } else if (isCard.value) {
    form.card_type = 'company'
    form.storage_status = props.asTemplate ? null : 'desiccator'
  }
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      hydrate()
      void loadReferences()
    }
  },
)

const nameRules = [(v: string) => !!v?.trim() || t('itemForm.nameRequired')]
// Both mirror server rules, so the user is told before the round-trip.
const serialRules = [
  (v: string) => !bySerial.value || props.asTemplate || !!v?.trim() || t('itemForm.serialRequired'),
]
const quantityRules = [
  (v: number) => !byQuantity.value || Number(v) >= 1 || t('itemForm.quantityMin'),
]
// Mirrors the server rule, so the user is told before the round-trip instead of
// bouncing off a 400.
const stateNoteRules = [
  (v: string) => !stateNoteRequired.value || !!v?.trim() || t('dlg.state.noteError'),
]

function buildPayload(): ItemCreate | ItemUpdate {
  const clean = (s: string) => (s.trim() === '' ? null : s.trim())
  const base: ItemUpdate = {
    name: form.name.trim(),
    industry: form.industry || null,
    project: form.project || null,
    team: clean(form.team),
    state: form.state,
    description: clean(form.description),
    dmz: clean(form.dmz),
    location_id: form.location_id,
    manager_ids: form.manager_ids,
  }
  // Only send a note when the state actually moved — an unchanged state must
  // not attach a stray note to the item's history.
  if (props.mode === 'edit' && stateChanged.value && form.state_note.trim()) {
    base.state_note = form.state_note.trim()
  }
  if (isCard.value) {
    base.card_type = form.card_type
    base.responsible = clean(form.responsible)
    base.lead = clean(form.lead)
    base.production_date = clean(form.production_date)
    base.version = clean(form.version)
    // Send only the field that applies to this kind of card: a serial on a
    // commercial card is rejected outright, and a quantity on a serialised one
    // likewise — sending both would turn a valid form into a 400.
    base.serial = byQuantity.value ? null : clean(form.serial)
    base.quantity = byQuantity.value ? Number(form.quantity) || 1 : 1
    base.storage_status = form.storage_status
  }
  if (props.mode === 'create') {
    const payload: ItemCreate = { ...base, type: itemType.value } as ItemCreate
    payload.is_template = !!props.asTemplate
    if (showHierarchy.value) {
      payload.parent_id = form.parent_id
      payload.child_ids = form.child_ids
    }
    return payload
  }
  return base
}

async function submit() {
  const result = await formRef.value?.validate()
  if (result && !result.valid) return
  saving.value = true
  try {
    emit('submit', buildPayload())
  } finally {
    saving.value = false
  }
}

const dialogTitle = computed(() => {
  if (props.mode === 'edit') return t('itemForm.editOf', { name: props.item?.name })
  if (props.asTemplate) return t('itemForm.newTemplate', { type: TYPE_LABELS[itemType.value] })
  if (props.prefill) return t('itemForm.duplicateOf', { name: props.prefill.name })
  return t('itemForm.newOf', { type: TYPE_LABELS[itemType.value] })
})
</script>

<template>
  <v-dialog v-model="open" max-width="760" scrollable>
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center gap-2 pa-4">
        <v-icon
          :icon="mode === 'create' ? (asTemplate ? 'mdi-shape-square-plus' : 'mdi-plus-circle') : 'mdi-pencil'"
          color="primary"
        />
        <span class="text-h6">{{ dialogTitle }}</span>
      </v-card-title>
      <v-divider />

      <v-card-text class="pa-4" style="max-height: 68vh">
        <v-progress-linear v-if="loadingRefs" indeterminate color="primary" class="mb-3" />
        <v-alert
          v-if="asTemplate"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-3"
          icon="mdi-information-outline"
        >
          {{ $t('itemForm.templateNotice') }}
        </v-alert>
        <v-form ref="formRef" v-model="valid" @submit.prevent="submit">
          <v-row dense>
            <v-col cols="12" sm="6">
              <v-text-field v-model="form.name" :label="$t('itemForm.nameReq')" :rules="nameRules" />
            </v-col>
            <v-col cols="12" sm="6">
              <v-select
                v-model="form.state"
                :label="$t('fields.state')"
                :items="ITEM_STATES.map((s) => ({ title: STATE_LABELS[s], value: s }))"
              />
            </v-col>
            <!-- Transitions into or out of "faulty" must be explained (§5/§6/§7). -->
            <v-col v-if="stateChanged" cols="12">
              <v-textarea
                v-model="form.state_note"
                :label="stateNoteRequired ? $t('dlg.noteRequired') : $t('dlg.noteOptional')"
                :rules="stateNoteRules"
                rows="2"
                auto-grow
                density="comfortable"
                prepend-inner-icon="mdi-swap-horizontal"
                :hint="$t('itemForm.stateNoteHint')"
                persistent-hint
              />
            </v-col>

            <v-col cols="12" sm="4">
              <v-autocomplete
                v-model="form.industry"
                :label="$t('fields.industry')"
                :items="industryItems"
                clearable
                :no-data-text="$t('itemForm.catalogEmpty')"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <v-autocomplete
                v-model="form.project"
                :label="$t('fields.project')"
                :items="projectItems"
                clearable
                :no-data-text="$t('itemForm.catalogEmpty')"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <v-text-field v-model="form.team" :label="$t('fields.team')" />
            </v-col>

            <v-col cols="12" :sm="showHierarchy && allowedParents.length ? 6 : 12">
              <v-select
                v-model="form.location_id"
                :label="$t('fields.location')"
                clearable
                :items="locations.map((l) => ({ title: l.name, value: l.id }))"
              />
            </v-col>
            <v-col v-if="showHierarchy && allowedParents.length" cols="12" sm="6">
              <v-select
                v-model="form.parent_id"
                :label="$t('itemForm.parentLabel')"
                :hint="$t('itemForm.parentHint')"
                persistent-hint
                clearable
                :items="parentSelectItems"
              />
            </v-col>

            <!-- Bidirectional linking: pull existing items in as children -->
            <v-col v-if="showHierarchy && childTypes.length" cols="12">
              <v-autocomplete
                v-model="form.child_ids"
                :label="itemType === 'setup' ? $t('itemForm.includeChildrenSetup') : $t('itemForm.includeChildrenAssembly')"
                :hint="$t('itemForm.includeChildrenHint')"
                persistent-hint
                multiple
                chips
                closable-chips
                :items="childSelectItems"
              />
            </v-col>

            <v-col cols="12">
              <v-textarea v-model="form.description" :label="$t('fields.description')" rows="2" auto-grow />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field v-model="form.dmz" :label="$t('fields.dmz')" />
            </v-col>
            <v-col cols="12" sm="6">
              <v-autocomplete
                v-model="form.manager_ids"
                :label="$t('fields.managers')"
                multiple
                chips
                closable-chips
                :items="managers.map((m) => ({ title: m.full_name, value: m.id }))"
              />
            </v-col>

            <template v-if="isCard">
              <v-col cols="12">
                <v-divider class="my-2" />
                <div class="text-overline text-medium-emphasis">{{ $t('itemForm.cardDetails') }}</div>
              </v-col>
              <v-col cols="12" sm="6">
                <v-select
                  v-model="form.card_type"
                  :label="$t('fields.cardType')"
                  :items="CARD_TYPES.map((c) => ({ title: CARD_TYPE_LABELS[c], value: c }))"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-select
                  v-model="form.storage_status"
                  :label="$t('fields.storageStatus')"
                  clearable
                  :items="STORAGE_STATUSES.map((s) => ({ title: STORAGE_LABELS[s], value: s }))"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field v-model="form.responsible" :label="$t('fields.responsible')" />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field v-model="form.lead" :label="$t('fields.lead')" />
              </v-col>
              <v-col cols="12">
                <v-alert
                  v-if="form.card_type"
                  :type="byQuantity ? 'info' : 'success'"
                  variant="tonal"
                  density="compact"
                  :icon="byQuantity ? 'mdi-numeric' : 'mdi-barcode'"
                >
                  {{ byQuantity ? $t('itemForm.quantityCardNotice') : $t('itemForm.serialCardNotice') }}
                </v-alert>
              </v-col>
              <v-col cols="12" sm="4">
                <v-text-field v-model="form.production_date" :label="$t('fields.productionDate')" type="date" />
              </v-col>
              <v-col cols="12" sm="4">
                <v-text-field v-model="form.version" :label="$t('fields.version')" />
              </v-col>
              <!-- One field or the other, never both: which one is what makes a
                   commercial card a different thing from a serialised one. -->
              <v-col v-if="byQuantity" cols="12" sm="4">
                <v-text-field
                  v-model.number="form.quantity"
                  :label="$t('itemForm.quantityReq')"
                  :rules="quantityRules"
                  type="number"
                  min="1"
                  prepend-inner-icon="mdi-numeric"
                  :hint="$t('itemForm.quantityHint')"
                  persistent-hint
                />
              </v-col>
              <v-col v-else cols="12" sm="4">
                <v-text-field
                  v-model="form.serial"
                  :label="bySerial && !asTemplate ? $t('itemForm.serialReq') : $t('fields.serial')"
                  :rules="serialRules"
                  :disabled="!form.card_type"
                  prepend-inner-icon="mdi-barcode"
                  :hint="bySerial ? $t('itemForm.serialUniqueHint') : ''"
                  :persistent-hint="bySerial"
                />
              </v-col>
            </template>
          </v-row>
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
          :prepend-icon="direct ? 'mdi-content-save' : 'mdi-send'"
          @click="submit"
        >
          {{ direct ? $t('common.save') : $t('dlg.continueToProposal') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
