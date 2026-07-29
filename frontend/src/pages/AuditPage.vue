<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { auditApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { formatDateTime } from '@/constants'
import type { AuditOut } from '@/api/types'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const { t } = useI18n({ useScope: 'global' })

const view = ref<'all' | 'mine'>('all')
const period = ref<'day' | 'week' | 'month'>('week')
const limit = ref(50)
const entries = ref<AuditOut[]>([])
const loading = ref(false)
const search = ref('')

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

async function load() {
  loading.value = true
  try {
    entries.value =
      view.value === 'mine'
        ? await auditApi.myItems(period.value)
        : await auditApi.list({ limit: limit.value })
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
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
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-card-text class="d-flex flex-wrap align-center gap-4">
        <v-btn-toggle
          v-if="auth.isManager"
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
          v-if="view === 'mine'"
          v-model="period"
          :label="$t('audit.period')"
          hide-details
          density="comfortable"
          style="max-width: 160px"
          :items="[
            { title: $t('audit.lastDay'), value: 'day' },
            { title: $t('audit.lastWeek'), value: 'week' },
            { title: $t('audit.lastMonth'), value: 'month' },
          ]"
        />
        <v-select
          v-else
          v-model="limit"
          :label="$t('audit.show')"
          hide-details
          density="comfortable"
          style="max-width: 140px"
          :items="[25, 50, 100, 200]"
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
            v-if="item.item_id"
            href="#"
            class="font-weight-medium"
            @click.prevent="router.push(`/items/${item.item_id}`)"
          >
            {{ item.item_name || `#${item.item_id}` }}
          </a>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.action="{ item }">
          <v-chip :color="actionColor(item.action)" size="x-small" variant="tonal">
            {{ item.action }}
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
