<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { itemsApi, locationsApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import StateChip from '@/components/StateChip.vue'
import EmptyState from '@/components/EmptyState.vue'
import ItemFormDialog from '@/components/ItemFormDialog.vue'
import ProposeChangeDialog from '@/components/ProposeChangeDialog.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import type { ProposeContext } from '@/lib/propose'
import {
  CARD_TYPES,
  CARD_TYPE_LABELS,
  ITEM_STATES,
  STATE_LABELS,
  STORAGE_COLORS,
  STORAGE_LABELS,
  STORAGE_STATUSES,
  TYPE_LABELS,
  formatDate,
} from '@/constants'
import type {
  BulkAction,
  CardType,
  ItemCreate,
  ItemListOut,
  ItemState,
  ItemType,
  ItemUpdate,
  LocationOut,
  StorageStatus,
} from '@/api/types'

const props = defineProps<{
  type: ItemType
  icon: string
  subtitle: string
}>()

const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

const NAV_PLURAL: Record<ItemType, string> = {
  setup: 'nav.setups',
  assembly: 'nav.assemblies',
  card: 'nav.cards',
}
const NEW_KEY: Record<ItemType, string> = {
  setup: 'items.actions.newSetup',
  assembly: 'items.actions.newAssembly',
  card: 'items.actions.newCard',
}
const pageTitle = computed(() => t(NAV_PLURAL[props.type]))
const newLabel = computed(() => t(NEW_KEY[props.type]))

const items = ref<ItemListOut[]>([])
const loading = ref(false)
const search = ref('')

const filters = reactive<{
  state: ItemState | null
  card_type: CardType | null
  storage_status: StorageStatus | null
  desiccatorOnly: boolean
}>({
  state: null,
  card_type: null,
  storage_status: null,
  desiccatorOnly: false,
})

const isCards = computed(() => props.type === 'card')

async function load() {
  loading.value = true
  try {
    items.value = await itemsApi.list({
      type: props.type,
      state: filters.state ?? undefined,
      card_type: isCards.value ? filters.card_type ?? undefined : undefined,
      storage_status:
        isCards.value && !filters.desiccatorOnly ? filters.storage_status ?? undefined : undefined,
      limit: 500,
    })
    // drop selections that no longer exist
    const ids = new Set(items.value.map((i) => i.id))
    selected.value = selected.value.filter((id) => ids.has(id))
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

const displayItems = computed(() => {
  if (isCards.value && filters.desiccatorOnly) {
    return items.value.filter((i) => i.storage_status === 'desiccator')
  }
  return items.value
})

watch(
  () => [filters.state, filters.card_type, filters.storage_status],
  () => load(),
)

const headers = computed<Record<string, unknown>[]>(() => {
  const base: Record<string, unknown>[] = [
    { title: t('items.columns.name'), key: 'name', minWidth: '180' },
    { title: t('fields.state'), key: 'state', width: 120 },
  ]
  if (isCards.value) {
    base.push(
      { title: t('fields.cardType'), key: 'card_type', width: 130 },
      { title: t('items.columns.storage'), key: 'storage_status', width: 140 },
      { title: t('fields.version'), key: 'version', width: 110 },
      { title: t('fields.serial'), key: 'serial', width: 130 },
    )
  } else {
    base.push(
      { title: t('fields.industry'), key: 'industry' },
      { title: t('fields.project'), key: 'project' },
      { title: t('fields.team'), key: 'team' },
      { title: t('items.columns.contents'), key: 'children_count', align: 'center', width: 100 },
    )
  }
  base.push(
    { title: t('items.columns.location'), key: 'location_name' },
    { title: t('items.columns.managers'), key: 'manager_names', sortable: false },
    { title: t('items.columns.updated'), key: 'updated_at', width: 130 },
    { title: '', key: 'row_actions', sortable: false, align: 'end', width: 60 },
  )
  return base
})

function openItem(item: ItemListOut) {
  router.push(`/items/${item.id}`)
}

// ---- Create / duplicate flow ----------------------------------------------
const formOpen = ref(false)
const formPrefill = ref<Partial<ItemCreate> | null>(null)
const proposeOpen = ref(false)
const proposeCtx = ref<ProposeContext | null>(null)

function openCreate() {
  formPrefill.value = null
  formOpen.value = true
}

async function openDuplicate(row: ItemListOut) {
  try {
    const full = await itemsApi.get(row.id)
    formPrefill.value = {
      name: `${full.name} ${t('items.copySuffix')}`,
      industry: full.industry,
      project: full.project,
      team: full.team,
      state: full.state,
      description: full.description,
      dmz: full.dmz,
      location_id: full.location_id,
      card_type: full.card_type,
      responsible: full.responsible,
      lead: full.lead,
      version: full.version,
      storage_status: full.storage_status,
      // a duplicated unique card must get its own serial → leave blank
      serial: null,
      manager_ids: full.managers.map((m) => m.id),
    }
    formOpen.value = true
  } catch (e) {
    ui.error(e)
  }
}

async function onFormSubmit(payload: ItemCreate | ItemUpdate) {
  if (auth.canDirectEdit) {
    try {
      const created = await itemsApi.create(payload as ItemCreate)
      ui.success(t('items.createdToast', { type: TYPE_LABELS[props.type] }))
      formOpen.value = false
      router.push(`/items/${created.id}`)
    } catch (e) {
      ui.error(e)
    }
  } else {
    proposeCtx.value = {
      action: 'create',
      itemType: props.type,
      payload: payload as Record<string, unknown>,
      targetName: (payload as ItemCreate).name,
      summaryLines: [
        { label: t('fields.type'), value: TYPE_LABELS[props.type] },
        { label: t('fields.name'), value: (payload as ItemCreate).name },
      ],
    }
    formOpen.value = false
    proposeOpen.value = true
  }
}

// ---- Bulk operations (managers only) --------------------------------------
const selected = ref<number[]>([])
const bulkMode = ref<'move' | 'state' | 'delete' | null>(null)
const bulkLocationId = ref<number | null>(null)
const bulkState = ref<ItemState | null>(null)
const bulkNote = ref('')
const bulkBusy = ref(false)
const locations = ref<LocationOut[]>([])

async function ensureLocations() {
  if (!locations.value.length) {
    try {
      locations.value = await locationsApi.list()
    } catch (e) {
      ui.error(e)
    }
  }
}

async function openBulk(mode: 'move' | 'state' | 'delete') {
  bulkNote.value = ''
  bulkLocationId.value = null
  bulkState.value = null
  if (mode === 'move') await ensureLocations()
  bulkMode.value = mode
}

async function runBulk() {
  const action: BulkAction | null =
    bulkMode.value === 'move' ? 'move' : bulkMode.value === 'state' ? 'state_change' : bulkMode.value === 'delete' ? 'delete' : null
  if (!action) return
  bulkBusy.value = true
  try {
    const res = await itemsApi.bulk({
      action,
      item_ids: selected.value,
      location_id: bulkMode.value === 'move' ? bulkLocationId.value : undefined,
      state: bulkMode.value === 'state' ? bulkState.value : undefined,
      note: bulkNote.value.trim() || undefined,
    })
    ui.success(t('items.bulk.done', { n: res.processed }))
    bulkMode.value = null
    selected.value = []
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    bulkBusy.value = false
  }
}

const bulkStateNoteRequired = computed(
  () => bulkMode.value === 'state' && bulkState.value === 'faulty',
)
const bulkConfirmDisabled = computed(() => {
  if (bulkMode.value === 'move') return bulkLocationId.value == null
  if (bulkMode.value === 'state') return bulkState.value == null || (bulkStateNoteRequired.value && !bulkNote.value.trim())
  return false
})

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader :title="pageTitle" :subtitle="subtitle" :icon="icon">
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="load" />
        <v-btn
          v-if="auth.canPropose"
          color="primary"
          :prepend-icon="auth.canDirectEdit ? 'mdi-plus' : 'mdi-file-plus-outline'"
          @click="openCreate"
        >
          {{ auth.canDirectEdit ? newLabel : $t('items.proposeNew') }}
        </v-btn>
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-card-text>
        <v-row dense align="center">
          <v-col cols="12" md="4">
            <v-text-field
              v-model="search"
              :label="$t('common.search')"
              prepend-inner-icon="mdi-magnify"
              clearable
              hide-details
              density="comfortable"
            />
          </v-col>
          <v-col cols="6" md="2">
            <v-select
              v-model="filters.state"
              :label="$t('fields.state')"
              clearable
              hide-details
              density="comfortable"
              :items="ITEM_STATES.map((s) => ({ title: STATE_LABELS[s], value: s }))"
            />
          </v-col>
          <template v-if="isCards">
            <v-col cols="6" md="2">
              <v-select
                v-model="filters.card_type"
                :label="$t('fields.cardType')"
                clearable
                hide-details
                density="comfortable"
                :items="CARD_TYPES.map((c) => ({ title: CARD_TYPE_LABELS[c], value: c }))"
              />
            </v-col>
            <v-col cols="6" md="2">
              <v-select
                v-model="filters.storage_status"
                :label="$t('items.columns.storage')"
                clearable
                hide-details
                density="comfortable"
                :disabled="filters.desiccatorOnly"
                :items="STORAGE_STATUSES.map((s) => ({ title: STORAGE_LABELS[s], value: s }))"
              />
            </v-col>
            <v-col cols="6" md="2">
              <v-switch
                v-model="filters.desiccatorOnly"
                :label="$t('items.desiccatorOnly')"
                color="cyan-darken-2"
                hide-details
                density="comfortable"
              />
            </v-col>
          </template>
        </v-row>
      </v-card-text>
      <v-divider />

      <!-- Bulk action bar -->
      <v-expand-transition>
        <div v-if="auth.canDirectEdit && selected.length" class="bulk-bar d-flex align-center flex-wrap gap-2 px-4 py-2">
          <v-chip color="primary" variant="flat" size="small">
            {{ $t('items.bulk.selected', { n: selected.length }) }}
          </v-chip>
          <v-btn size="small" variant="tonal" prepend-icon="mdi-map-marker-radius" @click="openBulk('move')">
            {{ $t('items.actions.move') }}
          </v-btn>
          <v-btn size="small" variant="tonal" prepend-icon="mdi-swap-horizontal" @click="openBulk('state')">
            {{ $t('items.actions.changeState') }}
          </v-btn>
          <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click="openBulk('delete')">
            {{ $t('common.delete') }}
          </v-btn>
          <v-spacer />
          <v-btn size="small" variant="text" @click="selected = []">{{ $t('items.bulk.clear') }}</v-btn>
        </div>
      </v-expand-transition>

      <v-data-table
        v-model="selected"
        :headers="headers as any"
        :items="displayItems"
        :loading="loading"
        :search="search"
        item-value="id"
        :show-select="auth.canDirectEdit"
        hover
        density="comfortable"
        :items-per-page="25"
        @click:row="(_: unknown, ctx: any) => openItem(ctx.item)"
      >
        <template #item.name="{ item }">
          <div class="font-weight-medium">{{ item.name }}</div>
        </template>
        <template #item.state="{ item }">
          <StateChip :state="item.state" />
        </template>
        <template #item.card_type="{ item }">
          <span v-if="item.card_type">{{ CARD_TYPE_LABELS[item.card_type as CardType] }}</span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.storage_status="{ item }">
          <v-chip
            v-if="item.storage_status"
            :color="STORAGE_COLORS[item.storage_status as StorageStatus]"
            size="x-small"
            variant="tonal"
          >
            {{ STORAGE_LABELS[item.storage_status as StorageStatus] }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.location_name="{ item }">
          <span v-if="item.location_name">
            <v-icon icon="mdi-map-marker" size="14" class="me-1" />{{ item.location_name }}
          </span>
          <span v-else class="text-medium-emphasis">{{ $t('items.unassigned') }}</span>
        </template>
        <template #item.manager_names="{ item }">
          <div class="d-flex flex-wrap gap-1">
            <v-chip
              v-for="(m, i) in item.manager_names.slice(0, 2)"
              :key="i"
              size="x-small"
              variant="tonal"
            >
              {{ m }}
            </v-chip>
            <v-chip
              v-if="item.manager_names.length > 2"
              size="x-small"
              variant="text"
            >
              +{{ item.manager_names.length - 2 }}
            </v-chip>
            <span v-if="!item.manager_names.length" class="text-medium-emphasis">—</span>
          </div>
        </template>
        <template #item.children_count="{ item }">
          <v-chip size="x-small" variant="tonal" color="primary">{{ item.children_count }}</v-chip>
        </template>
        <template #item.updated_at="{ item }">
          <span class="text-caption">{{ formatDate(item.updated_at) }}</span>
        </template>
        <template #item.industry="{ item }">
          {{ item.industry || '—' }}
        </template>
        <template #item.project="{ item }">
          {{ item.project || '—' }}
        </template>
        <template #item.team="{ item }">
          {{ item.team || '—' }}
        </template>
        <template #item.version="{ item }">
          {{ item.version || '—' }}
        </template>
        <template #item.serial="{ item }">
          {{ item.serial || '—' }}
        </template>
        <template #item.row_actions="{ item }">
          <v-menu location="bottom end">
            <template #activator="{ props: menu }">
              <v-btn v-bind="menu" icon="mdi-dots-vertical" size="small" variant="text" @click.stop />
            </template>
            <v-list density="compact" nav>
              <v-list-item prepend-icon="mdi-open-in-new" :title="$t('items.actions.open')" @click="openItem(item)" />
              <v-list-item
                v-if="auth.canPropose"
                prepend-icon="mdi-content-duplicate"
                :title="$t('items.actions.duplicate')"
                @click="openDuplicate(item)"
              />
            </v-list>
          </v-menu>
        </template>

        <template #no-data>
          <EmptyState :icon="icon" :title="$t('items.empty')" :text="$t('items.emptyHint')" />
        </template>
        <template #loading>
          <v-skeleton-loader type="table-row@6" />
        </template>
      </v-data-table>
    </v-card>

    <ItemFormDialog
      v-model="formOpen"
      mode="create"
      :type="type"
      :prefill="formPrefill"
      :direct="auth.canDirectEdit"
      @submit="onFormSubmit"
    />
    <ProposeChangeDialog v-model="proposeOpen" :context="proposeCtx" @submitted="load" />

    <!-- Bulk move / state / delete -->
    <v-dialog :model-value="bulkMode === 'move'" max-width="480" @update:model-value="(v) => !v && (bulkMode = null)">
      <v-card rounded="lg">
        <v-card-title class="pa-4">{{ $t('items.bulk.moveTitle', { n: selected.length }) }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-select
            v-model="bulkLocationId"
            :label="$t('fields.location')"
            :items="locations.map((l) => ({ title: l.name, value: l.id }))"
          />
          <v-alert type="info" variant="tonal" density="compact">{{ $t('items.bulk.moveHint') }}</v-alert>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="bulkMode = null">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="bulkBusy" :disabled="bulkConfirmDisabled" @click="runBulk">
            {{ $t('items.actions.move') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="bulkMode === 'state'" max-width="480" @update:model-value="(v) => !v && (bulkMode = null)">
      <v-card rounded="lg">
        <v-card-title class="pa-4">{{ $t('items.bulk.stateTitle', { n: selected.length }) }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-select
            v-model="bulkState"
            :label="$t('fields.state')"
            :items="ITEM_STATES.map((s) => ({ title: STATE_LABELS[s], value: s }))"
          />
          <v-textarea
            v-model="bulkNote"
            :label="bulkStateNoteRequired ? $t('items.bulk.noteReq') : $t('items.bulk.note')"
            rows="2"
            auto-grow
          />
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="bulkMode = null">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="bulkBusy" :disabled="bulkConfirmDisabled" @click="runBulk">
            {{ $t('common.apply') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ConfirmDialog
      :model-value="bulkMode === 'delete'"
      :title="$t('items.bulk.deleteTitle')"
      :message="$t('items.bulk.deleteMsg', { n: selected.length })"
      :confirm-text="$t('common.delete')"
      color="error"
      icon="mdi-delete-alert"
      :loading="bulkBusy"
      @update:model-value="(v) => !v && (bulkMode = null)"
      @confirm="runBulk"
    />
  </v-container>
</template>

<style scoped>
.bulk-bar {
  background: rgb(var(--v-theme-primary), 0.06);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
