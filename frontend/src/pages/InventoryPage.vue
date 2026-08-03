<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { inventoryApi, itemsApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import {
  CARD_TRACKING,
  CARD_TYPES,
  CARD_TYPE_LABELS,
  formatDate,
  TRACKING_LABELS,
} from '@/constants'
import type {
  CardTracking,
  CardType,
  InventoryGroup,
  ItemListOut,
  ThresholdOut,
} from '@/api/types'

const auth = useAuthStore()
const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

const view = ref<'all' | 'desiccator'>('all')
const cardTypeFilter = ref<CardType | null>(null)
const groups = ref<InventoryGroup[]>([])
const loading = ref(false)
const expanded = ref<string[]>([])

const thresholds = ref<ThresholdOut[]>([])
const thresholdsLoading = ref(false)

const groupHeaders = computed(() => [
  { title: t('fields.cardType'), key: 'card_type', width: 130 },
  { title: t('inventory.cols.countedBy'), key: 'tracking', width: 130 },
  { title: t('fields.name'), key: 'name' },
  { title: t('fields.version'), key: 'version', width: 110 },
  { title: t('inventory.cols.produced'), key: 'production_date', width: 130 },
  { title: t('inventory.cols.total'), key: 'total', align: 'center', width: 90 },
  { title: t('inventory.cols.records'), key: 'records', align: 'center', width: 100 },
  { title: t('inventory.cols.inUse'), key: 'in_use', align: 'center', width: 90 },
  { title: t('inventory.cols.desiccator'), key: 'desiccator', align: 'center', width: 110 },
  { title: t('inventory.cols.assembled'), key: 'assembled', align: 'center', width: 110 },
  { title: '', key: 'data-table-expand', width: 48 },
])

function rowKey(g: InventoryGroup): string {
  return `${g.card_type}|${g.name}|${g.version ?? ''}|${g.production_date ?? ''}`
}

// A *model* is a card type + name. The table below splits each model by version
// and production batch, so a name with 8 boards across two versions shows up as
// 6 + 2 — correct, but it never showed the 8 anywhere, which is what made the
// count look wrong. These rows roll the split back up.
function modelKey(g: InventoryGroup): string {
  return `${g.card_type}|${g.name}`
}

const rows = computed(() => groups.value.map((g) => ({ ...g, model: modelKey(g) })))

interface ModelTotal {
  card_type: CardType
  name: string
  total: number
  in_use: number
  desiccator: number
  assembled: number
  rows: number
}

const modelTotals = computed(() => {
  const out: Record<string, ModelTotal> = {}
  for (const g of groups.value) {
    const key = modelKey(g)
    const m = (out[key] ??= {
      card_type: g.card_type,
      name: g.name,
      total: 0,
      in_use: 0,
      desiccator: 0,
      assembled: 0,
      rows: 0,
    })
    m.total += g.total
    m.in_use += g.in_use
    m.desiccator += g.desiccator
    m.assembled += g.assembled
    m.rows += 1
  }
  return out
})

async function loadGroups() {
  loading.value = true
  try {
    const ct = cardTypeFilter.value ?? undefined
    groups.value =
      view.value === 'desiccator'
        ? await inventoryApi.desiccator(ct)
        : await inventoryApi.cards(ct)
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

async function loadThresholds() {
  thresholdsLoading.value = true
  try {
    thresholds.value = await inventoryApi.thresholds()
  } catch (e) {
    ui.error(e)
  } finally {
    thresholdsLoading.value = false
  }
}

watch([view, cardTypeFilter], loadGroups)

// ---- Threshold management -------------------------------------------------
// A threshold is set on a card that exists, never on a typed-in name: the user
// picks from the cards in the system and the server derives the watched group
// from it. That is also what lets the alert link back to a real card.
const thresholdDialog = ref(false)
const thresholdForm = reactive<{
  item_id: number | null
  any_version: boolean
  min_quantity: number
}>({ item_id: null, any_version: false, min_quantity: 1 })
const thresholdSaving = ref(false)
const removeThresholdId = ref<number | null>(null)

const cards = ref<ItemListOut[]>([])
const cardsLoading = ref(false)

/** One entry per card *model*, not per board — twenty serialised copies of a
 *  model are one thing to set a minimum on. */
const cardOptions = computed(() => {
  const seen = new Map<string, { title: string; subtitle: string; value: number }>()
  for (const c of cards.value) {
    if (!c.card_type) continue
    const key = `${c.card_type}|${c.name}|${c.version ?? ''}`
    if (seen.has(key)) continue
    seen.set(key, {
      value: c.id,
      title: c.version ? `${c.name} · v${c.version}` : c.name,
      subtitle: `${CARD_TYPE_LABELS[c.card_type]} · ${TRACKING_LABELS[CARD_TRACKING[c.card_type]]}`,
    })
  }
  return [...seen.values()].sort((a, b) => a.title.localeCompare(b.title))
})

const selectedCard = computed(() =>
  cards.value.find((c) => c.id === thresholdForm.item_id) ?? null,
)

async function openThresholdDialog() {
  thresholdForm.item_id = null
  thresholdForm.any_version = false
  thresholdForm.min_quantity = 1
  thresholdDialog.value = true
  cardsLoading.value = true
  try {
    cards.value = await itemsApi.list({ type: 'card', limit: 1000 })
  } catch (e) {
    ui.error(e)
  } finally {
    cardsLoading.value = false
  }
}

async function saveThreshold() {
  if (thresholdForm.item_id == null) return
  thresholdSaving.value = true
  try {
    await inventoryApi.createThreshold({
      item_id: thresholdForm.item_id,
      any_version: thresholdForm.any_version,
      min_quantity: Number(thresholdForm.min_quantity),
    })
    ui.success(t('inventory.saved'))
    thresholdDialog.value = false
    await Promise.all([loadThresholds(), loadGroups()])
  } catch (e) {
    ui.error(e)
  } finally {
    thresholdSaving.value = false
  }
}

async function confirmRemoveThreshold() {
  if (removeThresholdId.value == null) return
  try {
    await inventoryApi.removeThreshold(removeThresholdId.value)
    ui.success(t('inventory.removed'))
    await loadThresholds()
  } catch (e) {
    ui.error(e)
  } finally {
    removeThresholdId.value = null
  }
}

const lowCount = computed(() => thresholds.value.filter((t) => t.is_low).length)

onMounted(() => {
  void loadGroups()
  void loadThresholds()
})
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader
      :title="$t('nav.inventory')"
      :subtitle="$t('inventory.subtitle')"
      icon="mdi-warehouse"
    >
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="loadGroups" />
      </template>
    </PageHeader>

    <v-card variant="flat" border class="mb-6">
      <v-card-text>
        <div class="d-flex flex-wrap align-center gap-4">
          <v-btn-toggle
            v-model="view"
            color="primary"
            variant="outlined"
            density="comfortable"
            mandatory
            rounded="lg"
          >
            <v-btn value="all" prepend-icon="mdi-view-grid-outline">{{ $t('inventory.allCards') }}</v-btn>
            <v-btn value="desiccator" prepend-icon="mdi-water-off">{{ $t('inventory.desiccator') }}</v-btn>
          </v-btn-toggle>
          <v-spacer />
          <v-select
            v-model="cardTypeFilter"
            :label="$t('fields.cardType')"
            clearable
            hide-details
            density="comfortable"
            style="max-width: 220px"
            :items="CARD_TYPES.map((c) => ({ title: CARD_TYPE_LABELS[c], value: c }))"
          />
        </div>
      </v-card-text>
      <v-divider />

      <v-data-table
        v-model:expanded="expanded"
        :headers="groupHeaders as any"
        :items="rows"
        :loading="loading"
        :item-value="rowKey"
        :group-by="[{ key: 'model', order: 'asc' }]"
        show-expand
        density="comfortable"
        :items-per-page="25"
      >
        <!-- The model's own total, above its version/batch split. -->
        <template #group-header="{ item, columns, toggleGroup, isGroupOpen }">
          <tr class="model-row">
            <td :colspan="columns.length" class="py-2">
              <div class="d-flex align-center flex-wrap gap-2">
                <v-btn
                  :icon="isGroupOpen(item) ? '$expand' : '$next'"
                  size="small"
                  variant="text"
                  density="comfortable"
                  @click="toggleGroup(item)"
                />
                <span class="font-weight-bold">{{ modelTotals[item.value]?.name }}</span>
                <v-chip size="x-small" variant="tonal" color="primary">
                  {{ CARD_TYPE_LABELS[modelTotals[item.value]?.card_type as CardType] }}
                </v-chip>
                <v-chip size="small" variant="flat" color="blue-grey" class="font-weight-bold">
                  {{ modelTotals[item.value]?.total }}
                </v-chip>
                <span class="text-caption text-medium-emphasis">
                  {{ $t('inventory.modelTotal', {
                    total: modelTotals[item.value]?.total ?? 0,
                    n: modelTotals[item.value]?.rows ?? 0,
                  }) }}
                </span>
                <v-spacer />
                <span class="text-caption text-cyan-darken-2">
                  {{ $t('inventory.modelDesiccator', { n: modelTotals[item.value]?.desiccator ?? 0 }) }}
                </span>
              </div>
            </td>
          </tr>
        </template>
        <template #item.card_type="{ item }">
          <v-chip size="small" variant="tonal" color="primary">
            {{ CARD_TYPE_LABELS[item.card_type as CardType] }}
          </v-chip>
        </template>
        <!-- Where the number in "total" comes from. Without it, a commercial
             card's stock and a batch of serialised boards look identical. -->
        <template #item.tracking="{ item }">
          <v-chip
            v-if="item.tracking"
            size="x-small"
            variant="outlined"
            :color="item.tracking === 'quantity' ? 'info' : 'teal'"
            :prepend-icon="item.tracking === 'quantity' ? 'mdi-numeric' : 'mdi-barcode'"
          >
            {{ TRACKING_LABELS[item.tracking as CardTracking] }}
          </v-chip>
        </template>
        <template #item.records="{ item }">
          <span class="text-medium-emphasis">{{ item.records }}</span>
        </template>
        <template #item.name="{ item }">
          <span class="font-weight-medium">{{ item.name }}</span>
        </template>
        <template #item.version="{ item }">{{ item.version || '—' }}</template>
        <template #item.production_date="{ item }">{{ formatDate(item.production_date) }}</template>
        <template #item.total="{ item }">
          <v-chip size="small" variant="flat" color="blue-grey">{{ item.total }}</v-chip>
        </template>
        <template #item.in_use="{ item }">
          <span :class="item.in_use ? 'text-green font-weight-bold' : 'text-medium-emphasis'">
            {{ item.in_use }}
          </span>
        </template>
        <template #item.desiccator="{ item }">
          <span :class="item.desiccator ? 'text-cyan-darken-2 font-weight-bold' : 'text-medium-emphasis'">
            {{ item.desiccator }}
          </span>
        </template>
        <template #item.assembled="{ item }">
          <span :class="item.assembled ? 'text-indigo font-weight-bold' : 'text-medium-emphasis'">
            {{ item.assembled }}
          </span>
        </template>
        <template #expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="py-3">
              <!-- Spell the arithmetic out. "Where does 25 come from?" was the
                   actual complaint, and it has a different answer per kind. -->
              <div class="text-caption mb-2">
                {{
                  item.tracking === 'quantity'
                    ? $t('inventory.explainQuantity', { total: item.total, records: item.records })
                    : $t('inventory.explainSerial', { total: item.total, records: item.records })
                }}
              </div>
              <template v-if="item.serials.length">
                <div class="d-flex flex-wrap gap-2">
                  <v-chip
                    v-for="s in item.serials"
                    :key="s"
                    size="small"
                    variant="outlined"
                    prepend-icon="mdi-barcode"
                  >
                    {{ s }}
                  </v-chip>
                </div>
              </template>
              <span v-else class="text-caption text-medium-emphasis">
                {{ $t('inventory.noSerials') }}
              </span>
            </td>
          </tr>
        </template>
        <template #no-data>
          <EmptyState icon="mdi-warehouse" :title="$t('inventory.noInventory')" />
        </template>
      </v-data-table>
    </v-card>

    <!-- Thresholds -->
    <v-card variant="flat" border>
      <v-card-title class="d-flex align-center gap-2">
        <v-icon icon="mdi-gauge-low" color="warning" />
        <span class="text-subtitle-1 font-weight-bold">{{ $t('inventory.thresholdsTitle') }}</span>
        <v-chip v-if="lowCount" size="small" color="error" variant="flat">
          {{ $t('inventory.lowCount', { n: lowCount }) }}
        </v-chip>
        <v-spacer />
        <v-btn
          v-if="auth.canPropose"
          size="small"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-plus"
          @click="openThresholdDialog"
        >
          {{ $t('inventory.addThreshold') }}
        </v-btn>
      </v-card-title>
      <v-divider />
      <v-table v-if="thresholds.length" density="comfortable">
        <thead>
          <tr>
            <th>{{ $t('fields.cardType') }}</th>
            <th>{{ $t('inventory.cols.countedBy') }}</th>
            <th>{{ $t('fields.name') }}</th>
            <th>{{ $t('fields.version') }}</th>
            <th class="text-center">{{ $t('inventory.thCurrent') }}</th>
            <th class="text-center">{{ $t('inventory.thMinimum') }}</th>
            <th class="text-center">{{ $t('inventory.thStatus') }}</th>
            <th>{{ $t('inventory.thOwner') }}</th>
            <th v-if="auth.canDirectEdit"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="t in thresholds"
            :key="t.id"
            :class="t.is_low ? 'bg-error-lighten-5' : ''"
          >
            <td>
              <v-chip size="x-small" variant="tonal">{{ CARD_TYPE_LABELS[t.card_type] }}</v-chip>
            </td>
            <td>
              <span v-if="t.tracking" class="text-caption text-medium-emphasis">
                {{ TRACKING_LABELS[t.tracking] }}
              </span>
            </td>
            <td class="font-weight-medium">
              <!-- The threshold was set from a real card, so it can open it. -->
              <RouterLink v-if="t.item_id" :to="`/items/${t.item_id}`" class="text-primary">
                {{ t.name }}
              </RouterLink>
              <span v-else>{{ t.name }}</span>
            </td>
            <td>
              <span v-if="t.version">{{ t.version }}</span>
              <span v-else class="text-caption text-medium-emphasis">
                {{ $t('inventory.allVersions') }}
              </span>
            </td>
            <td class="text-center">
              <span :class="t.is_low ? 'text-error font-weight-bold' : 'font-weight-medium'">
                {{ t.current_quantity }}
              </span>
            </td>
            <td class="text-center">{{ t.min_quantity }}</td>
            <td class="text-center">
              <v-chip v-if="t.is_low" size="x-small" color="error" variant="flat">{{ $t('inventory.lowStock') }}</v-chip>
              <v-chip v-else size="x-small" color="success" variant="tonal">{{ $t('inventory.ok') }}</v-chip>
            </td>
            <td class="text-caption">{{ t.editor_email || '—' }}</td>
            <td v-if="auth.canDirectEdit" class="text-end">
              <v-btn
                icon="mdi-delete-outline"
                size="x-small"
                variant="text"
                color="error"
                @click="removeThresholdId = t.id"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
      <EmptyState
        v-else
        icon="mdi-gauge-empty"
        :title="$t('inventory.noThresholds')"
        :text="$t('inventory.noThresholdsHint')"
      />
    </v-card>

    <!-- Add threshold dialog -->
    <v-dialog v-model="thresholdDialog" max-width="520">
      <v-card rounded="lg">
        <v-card-title class="pa-4">{{ $t('inventory.addTitle') }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <!-- Typing filters the existing cards; there is no way to invent one,
               which is what keeps a threshold pointing at something real. -->
          <v-autocomplete
            v-model="thresholdForm.item_id"
            :label="$t('inventory.pickCard')"
            :items="cardOptions"
            :loading="cardsLoading"
            :no-data-text="cardsLoading ? $t('common.loading') : $t('inventory.noCardsToWatch')"
            item-title="title"
            item-value="value"
            autofocus
            class="mb-1"
            prepend-inner-icon="mdi-memory"
            :hint="$t('inventory.pickCardHint')"
            persistent-hint
          >
            <template #item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
            </template>
          </v-autocomplete>

          <v-checkbox
            v-if="selectedCard?.version"
            v-model="thresholdForm.any_version"
            :label="$t('inventory.anyVersion', { version: selectedCard.version })"
            color="primary"
            density="compact"
            hide-details
            class="mb-2"
          />

          <v-text-field
            v-model.number="thresholdForm.min_quantity"
            :label="$t('inventory.minQty')"
            type="number"
            min="0"
          />
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="thresholdDialog = false">{{ $t('common.cancel') }}</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="thresholdSaving"
            :disabled="thresholdForm.item_id == null"
            @click="saveThreshold"
          >
            {{ $t('common.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ConfirmDialog
      :model-value="removeThresholdId !== null"
      :title="$t('inventory.removeTitle')"
      :confirm-text="$t('inventory.remove')"
      @update:model-value="(v) => !v && (removeThresholdId = null)"
      @confirm="confirmRemoveThreshold"
    />
  </v-container>
</template>

<style scoped>
.model-row {
  background: rgba(var(--v-theme-on-surface), 0.035);
}
</style>
