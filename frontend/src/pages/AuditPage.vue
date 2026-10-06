<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { auditApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { auditActionLabel, formatDateTime } from '@/constants'
import type { AuditOut, AuditPeriod } from '@/api/types'
import { downloadBlob } from '@/utils/download'

const ui = useUiStore()
const router = useRouter()
const { t } = useI18n({ useScope: 'global' })

const view = ref<'all' | 'mine'>('all')
const period = ref<AuditPeriod>('month')
const limit = ref(500)
const entries = ref<AuditOut[]>([])
const loading = ref(false)
const exporting = ref(false)
const search = ref('')

const PERIODS: AuditPeriod[] = ['day', 'week', 'month', 'half_year', 'year', 'all']
const periodItems = computed(() => PERIODS.map((p) => ({ title: t(`audit.periods.${p}`), value: p })))

const headers = computed(() => [
  { title: t('audit.when'), key: 'created_at', width: 190 },
  { title: t('audit.item'), key: 'item_name' },
  { title: t('audit.action'), key: 'action', width: 150 },
  { title: t('audit.summary'), key: 'summary' },
  { title: t('audit.by'), key: 'user_name', width: 160 },
])

function actionColor(action: string): string {
  const a = action.toLowerCase()
  if (a.includes('create')) return 'success'
  if (a.includes('delete')) return 'error'
  if (a.includes('approve')) return 'success'
  if (a.includes('reject')) return 'error'
  if (a.includes('state')) return 'primary'
  if (a.includes('move')) return 'info'
  return 'blue-grey'
}

function query() {
  return { period: period.value, mine: view.value === 'mine', limit: limit.value }
}

async function load() {
  loading.value = true
  try {
    entries.value = await auditApi.list(query())
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

async function exportExcel() {
  exporting.value = true
  try {
    const blob = await auditApi.export({ ...query(), limit: undefined, search: search.value || undefined })
    downloadBlob(blob, `lattice_audit_${view.value}_${period.value}.xlsx`)
    ui.success(t('audit.exported'))
  } catch (e) {
    ui.error(e)
  } finally {
    exporting.value = false
  }
}

function openEntry(a: AuditOut) {
  if (a.item_id) router.push(`/items/${a.item_id}`)
  else if (a.template_id) router.push(`/templates/${a.template_id}`)
}

watch([view, period, limit], load)

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader
      :title="$t('nav.audit')"
      :subtitle="$t('audit.subtitle')"
      icon="mdi-history"
    >
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="load" />
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-microsoft-excel" :loading="exporting" @click="exportExcel">
          {{ $t('audit.export') }}
        </v-btn>
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-card-text class="d-flex flex-wrap align-center gap-4">
        <v-btn-toggle
          v-model="view"
          color="primary"
          variant="outlined"
          density="comfortable"
          mandatory
          rounded="lg"
        >
          <v-btn value="all" prepend-icon="mdi-earth">{{ $t('audit.allActivity') }}</v-btn>
          <v-btn value="mine" prepend-icon="mdi-account-check">{{ $t('audit.myLinked') }}</v-btn>
        </v-btn-toggle>

        <v-select
          v-model="period"
          :label="$t('audit.period')"
          hide-details
          density="comfortable"
          style="max-width: 190px"
          :items="periodItems"
        />
        <v-select
          v-model="limit"
          :label="$t('audit.show')"
          hide-details
          density="comfortable"
          style="max-width: 120px"
          :items="[100, 500, 1000, 5000]"
        />

        <v-spacer />
        <v-text-field
          v-model="search"
          :label="$t('common.search')"
          prepend-inner-icon="mdi-magnify"
          clearable
          hide-details
          density="comfortable"
          style="max-width: 320px"
        />
      </v-card-text>
      <v-divider />

      <v-data-table
        :headers="headers as any"
        :items="entries"
        :loading="loading"
        :search="search"
        item-value="id"
        density="comfortable"
        :items-per-page="25"
      >
        <template #item.created_at="{ item }">
          <span class="text-caption">{{ formatDateTime(item.created_at) }}</span>
        </template>
        <template #item.item_name="{ item }">
          <a
            v-if="item.item_id || item.template_id"
            href="#"
            class="font-weight-medium"
            @click.prevent="openEntry(item)"
          >
            {{ item.item_name || `#${item.item_id ?? item.template_id}` }}
          </a>
          <span v-else-if="item.item_name"><bdi>{{ item.item_name }}</bdi></span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.action="{ item }">
          <v-chip :color="actionColor(item.action)" size="x-small" variant="tonal">
            {{ auditActionLabel(item.action) }}
          </v-chip>
        </template>
        <template #item.user_name="{ item }">
          {{ item.user_name || $t('audit.system') }}
        </template>
        <template #no-data>
          <EmptyState
            icon="mdi-history"
            :title="$t('audit.noRecords')"
            :text="view === 'mine' ? $t('audit.noMineHint') : $t('audit.noAllHint')"
          />
        </template>
      </v-data-table>
    </v-card>
  </v-container>
</template>
