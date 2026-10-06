<script setup lang="ts">
// Cards / assemblies / setups, grouped by template.
//
// A flat list of every unit stops being usable as the system grows, so the
// page shows one tile per template — its type and how many units are in each
// state (destroyed units are history and aren't counted) — and opening a tile
// lists that template's units: state, location, parent and serial.
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { itemsApi, templatesApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import StateChip from '@/components/StateChip.vue'
import EmptyState from '@/components/EmptyState.vue'
import ItemFormDialog from '@/components/ItemFormDialog.vue'
import ProposeChangeDialog from '@/components/ProposeChangeDialog.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import type { ProposeContext } from '@/lib/propose'
import {
  ACTIVE_STATES,
  CARD_TYPES,
  CARD_TYPE_COLORS,
  CARD_TYPE_LABELS,
  ITEM_STATES,
  STATE_COLORS,
  STATE_LABELS,
  STORAGE_COLORS,
  STORAGE_LABELS,
  TYPE_LABELS,
  isQuantityTracked,
} from '@/constants'
import type {
  BulkAction,
  CardType,
  ItemCreate,
  ItemListOut,
  ItemOut,
  ItemState,
  ItemType,
  ItemUpdate,
  TemplateOut,
  TemplateSummary,
} from '@/api/types'

const props = defineProps<{
  type: ItemType
  icon: string
  subtitle: string
}>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

const NAV_PLURAL: Record<ItemType, string> = {
  setup: 'nav.setups',
  assembly: 'nav.assemblies',
  card: 'nav.cards',
}
const pageTitle = computed(() => t(NAV_PLURAL[props.type]))
const isCards = computed(() => props.type === 'card')

// ── templates (tiles) ──
const templates = ref<TemplateSummary[]>([])
const loading = ref(false)
const search = ref('')
const cardType = ref<CardType | null>(null)

async function loadTemplates() {
  loading.value = true
  try {
    templates.value = await templatesApi.list({ type: props.type })
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

const shownTemplates = computed(() => {
  const q = search.value.trim().toLowerCase()
  return templates.value.filter(
    (tp) =>
      (!cardType.value || tp.card_type === cardType.value) &&
      (!q || tp.name.toLowerCase().includes(q) || tp.serial_prefix.toLowerCase().includes(q)),
  )
})

const totals = computed(() => {
  const out = { built: 0, ok: 0, faulty: 0, total: 0 }
  for (const tp of shownTemplates.value) {
    out.built += tp.counts.built
    out.ok += tp.counts.ok
    out.faulty += tp.counts.faulty
    out.total += tp.counts.total
  }
  return out
})

// ── the selected template's units ──
const selectedId = ref<number | null>(null)
const selected = computed(() => templates.value.find((tp) => tp.id === selectedId.value) ?? null)
const items = ref<ItemListOut[]>([])
const itemsLoading = ref(false)
const stateFilter = ref<ItemState | null>(null)
const showDestroyed = ref(false)
const itemSearch = ref('')
const unitsAnchor = ref<HTMLElement | null>(null)

async function loadItems() {
  if (!selectedId.value) {
    items.value = []
    return
  }
  itemsLoading.value = true
  try {
    items.value = await itemsApi.list({
      template_id: selectedId.value,
      state: stateFilter.value ?? undefined,
      include_destroyed: showDestroyed.value || stateFilter.value === 'destroyed',
    })
    const ids = new Set(items.value.map((i) => i.id))
    selectedRows.value = selectedRows.value.filter((id) => ids.has(id))
  } catch (e) {
    ui.error(e)
  } finally {
    itemsLoading.value = false
  }
}

function openTemplate(id: number) {
  if (selectedId.value === id) return
  selectedId.value = id
  router.replace({ query: { ...route.query, template: String(id) } })
  nextTick(() => unitsAnchor.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

function closeTemplate() {
  selectedId.value = null
  const { template: _t, ...rest } = route.query
  router.replace({ query: rest })
}

watch(selectedId, () => {
  stateFilter.value = null
  selectedRows.value = []
  void loadItems()
})
watch([stateFilter, showDestroyed], loadItems)

const headers = computed<Record<string, unknown>[]>(() => {
  const h: Record<string, unknown>[] = [
    { title: t('fields.serial'), key: 'serial', width: 150 },
    { title: t('fields.state'), key: 'state', width: 120 },
    { title: t('items.columns.location'), key: 'location_name' },
    { title: t('fields.parent'), key: 'parent_label' },
  ]
  if (isCards.value) h.push({ title: t('items.columns.storage'), key: 'storage_status', width: 140 })
  if (isCards.value && isQuantityTracked(selected.value?.card_type)) {
    h.push({ title: t('fields.quantity'), key: 'quantity', align: 'center', width: 100 })
  }
  if (!isCards.value) {
    h.push({ title: t('items.columns.contents'), key: 'children_count', align: 'center', width: 100 })
  }
  return h
})

// Parent only matters when there is one (assemblies/setups: shown only if any has a parent).
const visibleHeaders = computed(() =>
  headers.value.filter(
    (h) => h.key !== 'parent_label' || isCards.value || items.value.some((i) => i.parent_id),
  ),
)

// ── create ──
const formOpen = ref(false)
const formTemplateId = ref<number | null>(null)
const proposeOpen = ref(false)
const proposeCtx = ref<ProposeContext | null>(null)

function openCreate(templateId: number | null = null) {
  formTemplateId.value = templateId
  formOpen.value = true
}

function onSaved(item: ItemOut) {
  ui.success(t('items.createdToast', { type: TYPE_LABELS[props.type] }))
  router.push(`/items/${item.id}`)
}

function onPropose(payload: ItemCreate | ItemUpdate, tpl: TemplateOut) {
  proposeCtx.value = {
    action: 'create',
    itemType: tpl.type,
    templateId: tpl.id,
    payload: payload as Record<string, unknown>,
    targetName: tpl.name,
    summaryLines: [
      { label: t('fields.type'), value: TYPE_LABELS[tpl.type] },
      { label: t('itemForm.template'), value: tpl.name },
    ],
  }
  proposeOpen.value = true
}

// ── bulk (managers) ──
const selectedRows = ref<number[]>([])
const bulkMode = ref<'move' | 'state' | 'delete' | null>(null)
const bulk = reactive<{ locationId: number | null; state: ItemState | null; note: string }>({
  locationId: null,
  state: null,
  note: '',
})
const bulkBusy = ref(false)

async function openBulk(mode: 'move' | 'state' | 'delete') {
  Object.assign(bulk, { locationId: null, state: null, note: '' })
  if (mode === 'move') await refs.ensure()
  bulkMode.value = mode
}

const selectedLinked = computed(() =>
  items.value.filter((i) => selectedRows.value.includes(i.id) && i.parent_id),
)
const bulkNoteRequired = computed(
  () =>
    bulkMode.value === 'state' &&
    bulk.state !== null &&
    (bulk.state === 'faulty' ||
      items.value.some((i) => selectedRows.value.includes(i.id) && i.state === 'faulty')),
)
const bulkDisabled = computed(() => {
  if (bulkMode.value === 'move') return bulk.locationId == null || selectedLinked.value.length > 0
  if (bulkMode.value === 'state') return bulk.state == null || (bulkNoteRequired.value && !bulk.note.trim())
  return false
})

async function runBulk() {
  const action: BulkAction =
    bulkMode.value === 'move' ? 'move' : bulkMode.value === 'state' ? 'state_change' : 'delete'
  bulkBusy.value = true
  try {
    const res = await itemsApi.bulk({
      action,
      item_ids: selectedRows.value,
      location_id: bulkMode.value === 'move' ? bulk.locationId : undefined,
      state: bulkMode.value === 'state' ? bulk.state : undefined,
      note: bulk.note.trim() || undefined,
    })
    ui.success(t('items.bulk.done', { n: res.processed }))
    bulkMode.value = null
    selectedRows.value = []
    await Promise.all([loadItems(), loadTemplates()])
  } catch (e) {
    ui.error(e)
  } finally {
    bulkBusy.value = false
  }
}

watch(
  () => route.query.template,
  (q) => {
    const id = q ? Number(q) : null
    if (id && id !== selectedId.value) selectedId.value = id
  },
)

onMounted(async () => {
  await loadTemplates()
  const q = route.query.template
  if (q) selectedId.value = Number(q)
})
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader :title="pageTitle" :subtitle="subtitle" :icon="icon">
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="loadTemplates(); loadItems()" />
        <v-btn variant="tonal" prepend-icon="mdi-shape-outline" :to="`/templates?type=${type}`">
          {{ $t('groups.manageTemplates') }}
        </v-btn>
        <v-btn
          v-if="auth.canPropose"
          color="primary"
          :prepend-icon="auth.canDirectEdit ? 'mdi-plus' : 'mdi-file-plus-outline'"
          @click="openCreate(selectedId)"
        >
          {{ auth.canDirectEdit ? $t('groups.newItem', { type: TYPE_LABELS[type] }) : $t('items.proposeNew') }}
        </v-btn>
      </template>
    </PageHeader>

    <!-- filters + totals -->
    <v-card variant="flat" border class="mb-4">
      <v-card-text class="d-flex flex-wrap align-center gap-3">
        <v-text-field
          v-model="search"
          :label="$t('groups.searchTemplates')"
          prepend-inner-icon="mdi-magnify"
          clearable
          hide-details
          density="comfortable"
          style="max-width: 320px"
        />
        <v-select
          v-if="isCards"
          v-model="cardType"
          :label="$t('fields.cardType')"
          :items="CARD_TYPES.map((c) => ({ title: CARD_TYPE_LABELS[c], value: c }))"
          clearable
          hide-details
          density="comfortable"
          style="max-width: 220px"
        />
        <v-spacer />
        <div class="d-flex flex-wrap align-center gap-2">
          <span class="text-caption text-medium-emphasis">{{ $t('groups.totals') }}</span>
          <v-chip v-for="s in ACTIVE_STATES" :key="s" :color="STATE_COLORS[s]" size="small" variant="tonal">
            {{ STATE_LABELS[s] }} · {{ totals[s as 'built' | 'ok' | 'faulty'] }}
          </v-chip>
          <v-chip size="small" variant="outlined">{{ $t('groups.total') }} · {{ totals.total }}</v-chip>
        </div>
      </v-card-text>
    </v-card>

    <!-- one tile per template -->
    <v-row v-if="loading && !templates.length">
      <v-col v-for="n in 6" :key="n" cols="12" sm="6" lg="4">
        <v-skeleton-loader type="article" height="130" />
      </v-col>
    </v-row>
    <v-row v-else-if="shownTemplates.length" dense>
      <v-col v-for="tp in shownTemplates" :key="tp.id" cols="12" sm="6" lg="4" xl="3">
        <v-card
          variant="flat"
          border
          class="tile clickable-row"
          :class="{ 'tile--active': tp.id === selectedId }"
          @click="openTemplate(tp.id)"
        >
          <v-card-text>
            <div class="d-flex align-start gap-2">
              <div class="flex-grow-1 overflow-hidden">
                <div class="text-subtitle-1 font-weight-bold text-truncate"><bdi>{{ tp.name }}</bdi></div>
                <div class="d-flex flex-wrap align-center gap-2 mt-1">
                  <v-chip
                    v-if="tp.card_type"
                    :color="CARD_TYPE_COLORS[tp.card_type]"
                    size="x-small"
                    variant="flat"
                    label
                  >
                    {{ CARD_TYPE_LABELS[tp.card_type] }}
                  </v-chip>
                  <v-chip size="x-small" variant="outlined" label prepend-icon="mdi-barcode">
                    {{ tp.serial_prefix }}
                  </v-chip>
                </div>
              </div>
              <div class="text-end">
                <div class="text-h5 font-weight-bold">{{ tp.counts.total }}</div>
                <div class="text-caption text-medium-emphasis">{{ $t('groups.units') }}</div>
              </div>
            </div>
            <div class="state-bar mt-3" :title="$t('groups.byState')">
              <div
                v-for="s in ACTIVE_STATES"
                :key="s"
                class="state-bar__seg"
                :class="`bg-${STATE_COLORS[s]}`"
                :style="{ flexGrow: tp.counts[s as 'built' | 'ok' | 'faulty'] }"
              />
            </div>
            <div class="d-flex flex-wrap gap-3 mt-2 text-caption">
              <span v-for="s in ACTIVE_STATES" :key="s" class="d-flex align-center gap-1">
                <span class="dot" :class="`bg-${STATE_COLORS[s]}`" />
                <span>{{ STATE_LABELS[s] }}</span>
                <strong>{{ tp.counts[s as 'built' | 'ok' | 'faulty'] }}</strong>
              </span>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
    <v-card v-else variant="flat" border>
      <EmptyState :icon="icon" :title="$t('groups.noTemplates')" :text="$t('groups.noTemplatesHint')" />
    </v-card>

    <!-- the chosen template's units -->
    <div ref="unitsAnchor" />
    <v-card v-if="selected" variant="flat" border class="mt-6">
      <v-card-title class="d-flex flex-wrap align-center gap-2 pa-4">
        <v-icon :icon="icon" color="primary" />
        <span class="text-subtitle-1 font-weight-bold"><bdi>{{ selected.name }}</bdi></span>
        <v-chip size="small" variant="outlined" label>{{ selected.serial_prefix }}</v-chip>
        <v-spacer />
        <v-btn size="small" variant="text" prepend-icon="mdi-shape-outline" :to="`/templates/${selected.id}`">
          {{ $t('groups.viewTemplate') }}
        </v-btn>
        <v-btn
          v-if="auth.canPropose"
          size="small"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-plus"
          @click="openCreate(selected.id)"
        >
          {{ auth.canDirectEdit ? $t('groups.newOf', { name: selected.name }) : $t('items.proposeNew') }}
        </v-btn>
        <v-btn size="small" variant="text" icon="mdi-close" @click="closeTemplate" />
      </v-card-title>
      <v-divider />
      <v-card-text class="d-flex flex-wrap align-center gap-3">
        <v-chip-group v-model="stateFilter" color="primary">
          <v-chip v-for="s in ITEM_STATES" :key="s" :value="s" variant="outlined" filter size="small">
            {{ STATE_LABELS[s] }}
          </v-chip>
        </v-chip-group>
        <v-switch
          v-model="showDestroyed"
          :label="$t('groups.showDestroyed')"
          hide-details
          density="compact"
          color="grey"
        />
        <v-spacer />
        <v-text-field
          v-model="itemSearch"
          :label="$t('common.search')"
          prepend-inner-icon="mdi-magnify"
          clearable
          hide-details
          density="compact"
          style="max-width: 260px"
        />
      </v-card-text>

      <v-expand-transition>
        <div v-if="auth.canDirectEdit && selectedRows.length" class="bulk-bar d-flex align-center flex-wrap gap-2 px-4 py-2">
          <v-chip color="primary" variant="flat" size="small">
            {{ $t('items.bulk.selected', { n: selectedRows.length }) }}
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
          <v-btn size="small" variant="text" @click="selectedRows = []">{{ $t('items.bulk.clear') }}</v-btn>
        </div>
      </v-expand-transition>

      <v-data-table
        v-model="selectedRows"
        :headers="visibleHeaders as any"
        :items="items"
        :loading="itemsLoading"
        :search="itemSearch"
        item-value="id"
        :show-select="auth.canDirectEdit"
        hover
        density="comfortable"
        :items-per-page="25"
        @click:row="(_: unknown, ctx: any) => router.push(`/items/${ctx.item.id}`)"
      >
        <template #item.serial="{ item }">
          <span class="font-weight-medium font-mono">{{ item.serial }}</span>
        </template>
        <template #item.state="{ item }">
          <StateChip :state="item.state" />
        </template>
        <template #item.location_name="{ item }">
          <span v-if="item.location_name">
            <v-icon icon="mdi-map-marker" size="14" class="me-1" /><bdi>{{ item.location_name }}</bdi>
          </span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.parent_label="{ item }">
          <a v-if="item.parent_id" href="#" @click.prevent.stop="router.push(`/items/${item.parent_id}`)">
            <bdi>{{ item.parent_label }}</bdi>
          </a>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.storage_status="{ item }">
          <v-chip
            v-if="item.storage_status"
            :color="STORAGE_COLORS[item.storage_status]"
            size="x-small"
            variant="tonal"
          >
            {{ STORAGE_LABELS[item.storage_status] }}
          </v-chip>
        </template>
        <template #item.children_count="{ item }">
          <v-chip size="x-small" variant="tonal" color="primary">{{ item.children_count }}</v-chip>
        </template>
        <template #no-data>
          <EmptyState :icon="icon" :title="$t('items.empty')" :text="$t('groups.noUnitsHint')" />
        </template>
      </v-data-table>
    </v-card>

    <ItemFormDialog
      v-model="formOpen"
      mode="create"
      :type="type"
      :template-id="formTemplateId"
      :direct="auth.canDirectEdit"
      @saved="onSaved"
      @propose="onPropose"
    />
    <ProposeChangeDialog
      v-model="proposeOpen"
      :context="proposeCtx"
      @submitted="loadTemplates"
    />

    <!-- bulk move / state / delete -->
    <v-dialog :model-value="bulkMode === 'move'" max-width="480" @update:model-value="(v) => !v && (bulkMode = null)">
      <v-card rounded="lg">
        <v-card-title class="pa-4">{{ $t('items.bulk.moveTitle', { n: selectedRows.length }) }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-autocomplete
            v-model="bulk.locationId"
            :label="$t('fields.location')"
            :items="refs.locations.map((l) => ({ title: l.name, value: l.id }))"
          />
          <v-alert v-if="selectedLinked.length" type="warning" variant="tonal" density="compact" class="mb-2">
            {{ $t('items.bulk.moveLinked', { n: selectedLinked.length }) }}
          </v-alert>
          <v-alert type="info" variant="tonal" density="compact">{{ $t('items.bulk.moveHint') }}</v-alert>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="bulkMode = null">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="bulkBusy" :disabled="bulkDisabled" @click="runBulk">
            {{ $t('items.actions.move') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="bulkMode === 'state'" max-width="480" @update:model-value="(v) => !v && (bulkMode = null)">
      <v-card rounded="lg">
        <v-card-title class="pa-4">{{ $t('items.bulk.stateTitle', { n: selectedRows.length }) }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-select
            v-model="bulk.state"
            :label="$t('fields.state')"
            :items="ITEM_STATES.map((s) => ({ title: STATE_LABELS[s], value: s }))"
          />
          <v-textarea
            v-model="bulk.note"
            :label="bulkNoteRequired ? $t('items.bulk.noteReq') : $t('items.bulk.note')"
            rows="2"
            auto-grow
          />
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="bulkMode = null">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="bulkBusy" :disabled="bulkDisabled" @click="runBulk">
            {{ $t('common.apply') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ConfirmDialog
      :model-value="bulkMode === 'delete'"
      :title="$t('items.bulk.deleteTitle')"
      :message="$t('items.bulk.deleteMsg', { n: selectedRows.length })"
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
.tile {
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}
.tile--active {
  border-color: rgb(var(--v-theme-primary)) !important;
  box-shadow: 0 0 0 1px rgb(var(--v-theme-primary)) inset;
}
.state-bar {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.state-bar__seg {
  flex-basis: 0;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.font-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.bulk-bar {
  background: rgb(var(--v-theme-primary), 0.06);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
