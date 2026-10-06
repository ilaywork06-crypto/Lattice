<script setup lang="ts">
// Stock per card template.
//
// "Available" — what can be built with right now — is a card at a location in
// the desiccator group in state built or ok. The desiccator is a place: a card
// assembled into something that sits there is in it too. Cards outside the
// desiccator are presumably in use and don't count, nor do faulty or destroyed
// ones. Stock thresholds watch exactly that number.
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { inventoryApi, templatesApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import {
  CARD_TYPES,
  CARD_TYPE_COLORS,
  CARD_TYPE_LABELS,
  TRACKING_LABELS,
} from '@/constants'
import type { CardType, InventoryGroup, TemplateSummary, ThresholdOut } from '@/api/types'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const { t } = useI18n({ useScope: 'global' })

const groups = ref<InventoryGroup[]>([])
const thresholds = ref<ThresholdOut[]>([])
const loading = ref(false)
const view = ref<'all' | 'desiccator' | 'low'>('all')
const cardType = ref<CardType | null>(null)
const search = ref('')
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const expanded = ref<any[]>([])

async function load() {
  loading.value = true
  try {
    const [g, th] = await Promise.all([
      inventoryApi.cards(cardType.value ?? undefined),
      inventoryApi.thresholds(),
    ])
    groups.value = g
    thresholds.value = th
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

const shown = computed(() =>
  groups.value.filter((g) => {
    if (view.value === 'desiccator' && g.desiccator === 0) return false
    if (view.value === 'low' && !g.is_low) return false
    return true
  }),
)

const totals = computed(() =>
  shown.value.reduce(
    (acc, g) => ({
      total: acc.total + g.total,
      available: acc.available + g.available,
      desiccator: acc.desiccator + g.desiccator,
      in_use: acc.in_use + g.in_use,
      assembled: acc.assembled + g.assembled,
      faulty: acc.faulty + g.faulty,
    }),
    { total: 0, available: 0, desiccator: 0, in_use: 0, assembled: 0, faulty: 0 },
  ),
)

const headers = computed(() => [
  { title: t('inventory.cols.template'), key: 'name' },
  { title: t('fields.cardType'), key: 'card_type', width: 130 },
  { title: t('inventory.cols.available'), key: 'available', align: 'center', width: 120 },
  { title: t('inventory.cols.minimum'), key: 'min_quantity', align: 'center', width: 100 },
  { title: t('inventory.cols.desiccator'), key: 'desiccator', align: 'center', width: 110 },
  { title: t('inventory.cols.inUse'), key: 'in_use', align: 'center', width: 100 },
  { title: t('inventory.cols.assembled'), key: 'assembled', align: 'center', width: 110 },
  { title: t('inventory.cols.faulty'), key: 'faulty', align: 'center', width: 90 },
  { title: t('inventory.cols.total'), key: 'total', align: 'center', width: 90 },
  { title: '', key: 'data-table-expand', width: 48 },
])

// ── thresholds ──
const thOpen = ref(false)
const thSaving = ref(false)
const cardTemplates = ref<TemplateSummary[]>([])
const thForm = reactive<{ template_id: number | null; min_quantity: number; editor_email: string }>({
  template_id: null,
  min_quantity: 1,
  editor_email: '',
})
const removeTh = ref<ThresholdOut | null>(null)

async function openThreshold(templateId: number | null = null) {
  try {
    cardTemplates.value = await templatesApi.list({ type: 'card' })
  } catch (e) {
    ui.error(e)
  }
  const existing = thresholds.value.find((x) => x.template_id === templateId)
  Object.assign(thForm, {
    template_id: templateId,
    min_quantity: existing?.min_quantity ?? 1,
    editor_email: existing?.editor_email ?? '',
  })
  thOpen.value = true
}

async function saveThreshold() {
  if (!thForm.template_id) return
  thSaving.value = true
  try {
    await inventoryApi.createThreshold({
      template_id: thForm.template_id,
      min_quantity: Number(thForm.min_quantity) || 0,
      editor_email: thForm.editor_email.trim() || null,
    })
    ui.success(t('inventory.saved'))
    thOpen.value = false
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    thSaving.value = false
  }
}

async function confirmRemoveThreshold() {
  if (!removeTh.value) return
  try {
    await inventoryApi.removeThreshold(removeTh.value.id)
    ui.success(t('inventory.removed'))
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    removeTh.value = null
  }
}

const lowCount = computed(() => thresholds.value.filter((x) => x.is_low).length)

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader :title="$t('nav.inventory')" :subtitle="$t('inventory.subtitle')" icon="mdi-warehouse">
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="load" />
        <v-btn
          v-if="auth.isManager"
          variant="tonal"
          prepend-icon="mdi-water-off"
          :to="{ path: '/catalog', query: { tab: 'desiccator' } }"
        >
          {{ $t('inventory.defineDesiccator') }}
        </v-btn>
      </template>
    </PageHeader>

    <v-alert type="info" variant="tonal" density="compact" class="mb-4" icon="mdi-information-outline">
      {{ $t('inventory.availableExplainer') }}
    </v-alert>

    <!-- tiles -->
    <v-row dense class="mb-2">
      <v-col v-for="k in (['available', 'desiccator', 'in_use', 'assembled', 'faulty', 'total'] as const)" :key="k" cols="6" sm="4" md="2">
        <v-card variant="flat" border>
          <v-card-text>
            <div class="text-h5 font-weight-bold" :class="{ 'text-success': k === 'available', 'text-error': k === 'faulty' && totals.faulty }">
              {{ totals[k] }}
            </div>
            <div class="text-caption text-medium-emphasis">{{ $t('inventory.tiles.' + k) }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-card variant="flat" border>
      <v-card-text class="d-flex flex-wrap align-center gap-3">
        <v-btn-toggle v-model="view" mandatory color="primary" variant="outlined" density="comfortable" rounded="lg">
          <v-btn value="all">{{ $t('inventory.allCards') }}</v-btn>
          <v-btn value="desiccator" prepend-icon="mdi-water-off">{{ $t('inventory.desiccator') }}</v-btn>
          <v-btn value="low" prepend-icon="mdi-alert-decagram">{{ $t('inventory.onlyLow') }}</v-btn>
        </v-btn-toggle>
        <v-select
          v-model="cardType"
          :label="$t('fields.cardType')"
          :items="CARD_TYPES.map((c) => ({ title: CARD_TYPE_LABELS[c], value: c }))"
          clearable
          hide-details
          density="comfortable"
          style="max-width: 200px"
          @update:model-value="load"
        />
        <v-spacer />
        <v-text-field
          v-model="search"
          :label="$t('common.search')"
          prepend-inner-icon="mdi-magnify"
          clearable
          hide-details
          density="comfortable"
          style="max-width: 280px"
        />
      </v-card-text>
      <v-divider />
      <v-data-table
        v-model:expanded="expanded"
        :headers="headers as any"
        :items="shown"
        :loading="loading"
        :search="search"
        item-value="template_id"
        show-expand
        hover
        density="comfortable"
        :items-per-page="25"
      >
        <template #item.name="{ item }">
          <a href="#" class="font-weight-medium" @click.prevent="router.push(`/cards?template=${item.template_id}`)">
            <bdi>{{ item.name }}</bdi>
          </a>
          <div class="text-caption text-medium-emphasis">
            {{ item.serial_prefix }}<span v-if="item.tracking"> · {{ TRACKING_LABELS[item.tracking] }}</span>
          </div>
        </template>
        <template #item.card_type="{ item }">
          <v-chip :color="CARD_TYPE_COLORS[item.card_type]" size="x-small" variant="flat" label>
            {{ CARD_TYPE_LABELS[item.card_type] }}
          </v-chip>
        </template>
        <template #item.available="{ item }">
          <v-chip :color="item.is_low ? 'error' : 'success'" size="small" variant="tonal" class="font-weight-bold">
            {{ item.available }}
          </v-chip>
        </template>
        <template #item.desiccator="{ item }">
          {{ item.desiccator }}
          <div v-if="item.assembled_in_desiccator" class="text-caption text-medium-emphasis">
            {{ $t('inventory.assembledInDesiccator', { n: item.assembled_in_desiccator }) }}
          </div>
        </template>
        <template #item.min_quantity="{ item }">
          <a v-if="auth.canPropose" href="#" @click.prevent="openThreshold(item.template_id)">
            {{ item.min_quantity ?? $t('inventory.setMin') }}
          </a>
          <span v-else>{{ item.min_quantity ?? '—' }}</span>
        </template>
        <template #expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="py-3">
              <div class="text-caption text-medium-emphasis mb-2">
                {{ $t('inventory.availableSerials', { n: item.available_serials.length }) }}
              </div>
              <div v-if="item.available_serials.length" class="d-flex flex-wrap gap-1">
                <v-chip v-for="s in item.available_serials" :key="s" size="x-small" variant="outlined" label>{{ s }}</v-chip>
              </div>
              <span v-else class="text-caption">{{ $t('inventory.noneAvailable') }}</span>
            </td>
          </tr>
        </template>
        <template #no-data>
          <EmptyState icon="mdi-warehouse" :title="$t('inventory.noInventory')" />
        </template>
      </v-data-table>
    </v-card>

    <!-- thresholds -->
    <v-card variant="flat" border class="mt-6">
      <v-card-title class="d-flex align-center gap-2">
        <v-icon icon="mdi-alert-decagram" color="warning" />
        <span class="text-subtitle-1 font-weight-bold">{{ $t('inventory.thresholdsTitle') }}</span>
        <v-chip v-if="lowCount" size="small" color="error" variant="tonal">{{ $t('inventory.lowCount', { n: lowCount }) }}</v-chip>
        <v-spacer />
        <v-btn v-if="auth.canPropose" size="small" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openThreshold()">
          {{ $t('inventory.addThreshold') }}
        </v-btn>
      </v-card-title>
      <v-divider />
      <v-table v-if="thresholds.length" density="comfortable">
        <thead>
          <tr>
            <th>{{ $t('inventory.cols.template') }}</th>
            <th class="text-center">{{ $t('inventory.cols.available') }}</th>
            <th class="text-center">{{ $t('inventory.thMinimum') }}</th>
            <th>{{ $t('inventory.thOwner') }}</th>
            <th>{{ $t('inventory.thStatus') }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="th in thresholds" :key="th.id">
            <td class="font-weight-medium"><bdi>{{ th.name }}</bdi></td>
            <td class="text-center">{{ th.current_quantity }}</td>
            <td class="text-center">{{ th.min_quantity }}</td>
            <td>{{ th.editor_email || '—' }}</td>
            <td>
              <v-chip :color="th.is_low ? 'error' : 'success'" size="small" variant="flat">
                {{ th.is_low ? $t('inventory.lowStock') : $t('inventory.ok') }}
              </v-chip>
            </td>
            <td class="text-end">
              <v-btn v-if="auth.canPropose" icon="mdi-pencil" size="small" variant="text" @click="openThreshold(th.template_id)" />
              <v-btn v-if="auth.canDirectEdit" icon="mdi-delete-outline" size="small" variant="text" color="error" @click="removeTh = th" />
            </td>
          </tr>
        </tbody>
      </v-table>
      <EmptyState v-else icon="mdi-bell-off-outline" :title="$t('inventory.noThresholds')" :text="$t('inventory.noThresholdsHint')" />
    </v-card>

    <v-dialog v-model="thOpen" max-width="520">
      <v-card rounded="lg">
        <v-card-title class="pa-4">{{ $t('inventory.addTitle') }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-autocomplete
            v-model="thForm.template_id"
            :label="$t('inventory.pickTemplate')"
            :items="cardTemplates.map((tp) => ({ title: tp.name, value: tp.id, subtitle: tp.serial_prefix }))"
            item-title="title"
            item-value="value"
            :no-data-text="$t('inventory.noCardTemplates')"
          />
          <v-text-field v-model.number="thForm.min_quantity" :label="$t('inventory.minQty')" type="number" min="0" :hint="$t('inventory.minQtyHint')" persistent-hint />
          <v-text-field v-model="thForm.editor_email" :label="$t('inventory.extraEmail')" type="email" class="mt-2" />
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="thOpen = false">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="thSaving" :disabled="!thForm.template_id" @click="saveThreshold">
            {{ $t('common.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ConfirmDialog
      :model-value="removeTh !== null"
      :title="$t('inventory.removeTitle')"
      :confirm-text="$t('inventory.remove')"
      @update:model-value="(v) => !v && (removeTh = null)"
      @confirm="confirmRemoveThreshold"
    />
  </v-container>
</template>
