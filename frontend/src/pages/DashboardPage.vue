<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { auditApi, inventoryApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { auditActionLabel, formatDate, timeAgo } from '@/constants'
import type { AuditOut, InventorySummary, ThresholdOut } from '@/api/types'

const router = useRouter()
const ui = useUiStore()
const auth = useAuthStore()
const { t } = useI18n({ useScope: 'global' })

const summary = ref<InventorySummary | null>(null)
const lowStock = ref<ThresholdOut[]>([])
const activity = ref<AuditOut[]>([])
const loading = ref(true)

interface Stat {
  label: string
  value: number
  icon: string
  color: string
  to?: string
}

const stats = computed<Stat[]>(() => {
  const s = summary.value
  if (!s) return []
  return [
    { label: t('dash.stats.setups'), value: s.setups, icon: 'mdi-server', color: 'deep-purple', to: '/setups' },
    {
      label: t('dash.stats.assemblies'),
      value: s.assemblies,
      icon: 'mdi-cpu-64-bit',
      color: 'teal-darken-1',
      to: '/assemblies',
    },
    { label: t('dash.stats.cards'), value: s.cards, icon: 'mdi-memory', color: 'blue-darken-1', to: '/cards' },
    {
      label: t('dash.stats.cardsInUse'),
      value: s.cards_in_use,
      icon: 'mdi-power-plug',
      color: 'green-darken-1',
      to: '/cards',
    },
    {
      label: t('dash.stats.cardsAvailable'),
      value: s.cards_available,
      icon: 'mdi-water-off',
      color: 'cyan-darken-2',
      to: '/inventory',
    },
    { label: t('dash.stats.faultyItems'), value: s.faulty_items, icon: 'mdi-alert', color: 'error' },
    {
      label: t('dash.stats.pendingRequests'),
      value: s.pending_change_requests,
      icon: 'mdi-file-swap-outline',
      color: 'amber-darken-2',
      to: '/change-requests',
    },
    {
      label: t('dash.stats.lowStockAlerts'),
      value: s.low_stock_alerts,
      icon: 'mdi-alert-decagram',
      color: 'orange-darken-3',
      to: '/inventory',
    },
  ]
})

function auditIcon(action: string): string {
  const a = action.toLowerCase()
  if (a.includes('create')) return 'mdi-plus-circle'
  if (a.includes('delete')) return 'mdi-delete'
  if (a.includes('state')) return 'mdi-swap-horizontal'
  if (a.includes('move')) return 'mdi-map-marker-radius'
  if (a.includes('link')) return 'mdi-link-variant'
  if (a.includes('approve')) return 'mdi-check-decagram'
  if (a.includes('reject')) return 'mdi-close-circle'
  return 'mdi-pencil'
}

async function load() {
  loading.value = true
  try {
    const [s, ls, act] = await Promise.all([
      inventoryApi.summary(),
      inventoryApi.lowStock(),
      auditApi.list({ limit: 15 }),
    ])
    summary.value = s
    lowStock.value = ls
    activity.value = act
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader
      :title="$t('dash.welcome', { name: auth.fullName?.split(' ')[0] ?? '' })"
      :subtitle="$t('dash.subtitle')"
      icon="mdi-view-dashboard-outline"
    >
      <template #actions>
        <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="load">
          {{ $t('common.refresh') }}
        </v-btn>
      </template>
    </PageHeader>

    <!-- Stat cards -->
    <v-row>
      <template v-if="loading && !summary">
        <v-col v-for="n in 8" :key="n" cols="6" sm="4" md="3">
          <v-skeleton-loader type="image" height="118" class="rounded-lg" />
        </v-col>
      </template>
      <template v-else>
        <v-col v-for="stat in stats" :key="stat.label" cols="6" sm="4" md="3">
          <v-card
            class="stat-card"
            :class="{ 'clickable-row': stat.to }"
            variant="flat"
            border
            @click="stat.to && router.push(stat.to)"
          >
            <v-card-text class="d-flex align-center gap-3">
              <v-avatar :color="stat.color" variant="tonal" rounded="lg" size="48">
                <v-icon :icon="stat.icon" size="26" />
              </v-avatar>
              <div>
                <div class="text-h5 font-weight-bold"><bdi>{{ stat.value }}</bdi></div>
                <div class="text-caption text-medium-emphasis"><bdi>{{ stat.label }}</bdi></div>
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </template>
    </v-row>

    <v-row class="mt-2">
      <!-- Low stock -->
      <v-col cols="12" md="5">
        <v-card variant="flat" border height="100%">
          <v-card-title class="d-flex align-center gap-2">
            <v-icon icon="mdi-alert-decagram" color="warning" />
            <span class="text-subtitle-1 font-weight-bold">{{ $t('dash.lowStockTitle') }}</span>
            <v-spacer />
            <v-chip size="small" color="warning" variant="tonal">{{ lowStock.length }}</v-chip>
          </v-card-title>
          <v-divider />
          <template v-if="lowStock.length">
            <v-list lines="two" density="comfortable">
              <v-list-item v-for="t in lowStock" :key="t.id" @click="router.push(`/cards?template=${t.template_id}`)">
                <template #prepend>
                  <v-avatar color="warning" variant="tonal" size="40">
                    <v-icon icon="mdi-memory" />
                  </v-avatar>
                </template>
                <v-list-item-title class="font-weight-medium"><bdi>{{ t.name }}</bdi></v-list-item-title>
                <v-list-item-subtitle>
                  {{ $t('dash.inStock', { current: t.current_quantity, min: t.min_quantity }) }}
                </v-list-item-subtitle>
                <template #append>
                  <v-chip size="small" color="error" variant="flat">{{ $t('dash.low') }}</v-chip>
                </template>
              </v-list-item>
            </v-list>
          </template>
          <EmptyState
            v-else
            icon="mdi-check-circle-outline"
            :title="$t('dash.healthyTitle')"
            :text="$t('dash.healthyText')"
          />
        </v-card>
      </v-col>

      <!-- Recent activity -->
      <v-col cols="12" md="7">
        <v-card variant="flat" border height="100%">
          <v-card-title class="d-flex align-center gap-2">
            <v-icon icon="mdi-history" color="primary" />
            <span class="text-subtitle-1 font-weight-bold">{{ $t('dash.recentTitle') }}</span>
            <v-spacer />
            <v-btn size="small" variant="text" append-icon="mdi-arrow-right" to="/audit">
              {{ $t('dash.viewAll') }}
            </v-btn>
          </v-card-title>
          <v-divider />
          <template v-if="activity.length">
            <v-list lines="two" density="comfortable">
              <v-list-item
                v-for="a in activity"
                :key="a.id"
                :subtitle="a.summary"
                @click="a.item_id ? router.push(`/items/${a.item_id}`) : a.template_id && router.push(`/templates/${a.template_id}`)"
              >
                <template #prepend>
                  <v-avatar color="surface-variant" size="38">
                    <v-icon :icon="auditIcon(a.action)" size="20" />
                  </v-avatar>
                </template>
                <v-list-item-title class="font-weight-medium">
                  {{ a.item_name || auditActionLabel(a.action) }}
                </v-list-item-title>
                <template #append>
                  <div class="text-caption text-medium-emphasis text-end">
                    <div>{{ timeAgo(a.created_at) }}</div>
                    <div v-if="a.user_name"><bdi>{{ a.user_name }}</bdi></div>
                  </div>
                </template>
              </v-list-item>
            </v-list>
          </template>
          <EmptyState
            v-else
            icon="mdi-history"
            :title="$t('dash.recentEmptyTitle')"
            :text="$t('dash.recentEmptyText')"
          />
        </v-card>
      </v-col>
    </v-row>

    <div class="text-caption text-medium-emphasis text-center mt-6">
      {{ $t('dash.dataAsOf', { date: formatDate(new Date().toISOString()) }) }}
    </div>
  </v-container>
</template>
