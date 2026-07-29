<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { changeRequestsApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  CHANGE_ACTION_ICONS,
  CHANGE_ACTION_LABELS,
  CHANGE_STATUS_COLORS,
  TYPE_LABELS,
  formatDateTime,
  timeAgo,
} from '@/constants'
import type { ChangeRequestOut, ChangeStatus } from '@/api/types'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const { t } = useI18n({ useScope: 'global' })

const requests = ref<ChangeRequestOut[]>([])
const loading = ref(false)
const statusFilter = ref<ChangeStatus | null>(null)
const mineOnly = ref(!auth.isManager)

const statusOptions = computed<{ title: string; value: ChangeStatus | null }[]>(() => [
  { title: t('common.all'), value: null },
  { title: t('enums.changeStatus.pending'), value: 'pending' },
  { title: t('enums.changeStatus.approved'), value: 'approved' },
  { title: t('enums.changeStatus.rejected'), value: 'rejected' },
])

async function load() {
  loading.value = true
  try {
    requests.value = await changeRequestsApi.list({
      status: statusFilter.value ?? undefined,
      mine: mineOnly.value || undefined,
    })
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

watch([statusFilter, mineOnly], load)

// ---- Detail dialog --------------------------------------------------------
const detailOpen = ref(false)
const selected = ref<ChangeRequestOut | null>(null)
const reviewNote = ref('')
const reviewing = ref(false)

function openDetail(cr: ChangeRequestOut) {
  selected.value = cr
  reviewNote.value = ''
  detailOpen.value = true
}

const payloadRows = computed(() => {
  if (!selected.value) return []
  return Object.entries(selected.value.payload || {})
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => ({
      key: k,
      value: Array.isArray(v) ? v.join(', ') : String(v),
    }))
})

async function review(action: 'approve' | 'reject') {
  if (!selected.value) return
  reviewing.value = true
  try {
    if (action === 'approve') {
      await changeRequestsApi.approve(selected.value.id, reviewNote.value.trim() || undefined)
      ui.success(t('cr.approvedToast'))
    } else {
      await changeRequestsApi.reject(selected.value.id, reviewNote.value.trim() || undefined)
      ui.info(t('cr.rejectedToast'))
    }
    detailOpen.value = false
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    reviewing.value = false
  }
}

const pendingCount = computed(() => requests.value.filter((r) => r.status === 'pending').length)

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader
      :title="$t('nav.changeRequests')"
      :subtitle="$t('cr.subtitle')"
      icon="mdi-file-swap-outline"
    >
      <template #actions>
        <v-chip v-if="pendingCount" color="amber-darken-2" variant="tonal">
          {{ $t('cr.pendingCount', { n: pendingCount }) }}
        </v-chip>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="load" />
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-card-text class="d-flex flex-wrap align-center gap-4">
        <v-chip-group v-model="statusFilter" mandatory color="primary" selected-class="text-primary">
          <v-chip
            v-for="opt in statusOptions"
            :key="String(opt.value)"
            :value="opt.value"
            variant="outlined"
            filter
          >
            {{ opt.title }}
          </v-chip>
        </v-chip-group>
        <v-spacer />
        <v-switch
          v-if="auth.isManager"
          v-model="mineOnly"
          :label="$t('cr.myOnly')"
          color="primary"
          hide-details
          density="comfortable"
        />
      </v-card-text>
      <v-divider />

      <div v-if="loading" class="pa-4">
        <v-skeleton-loader type="list-item-two-line@5" />
      </div>
      <v-list v-else-if="requests.length" lines="two">
        <template v-for="(cr, i) in requests" :key="cr.id">
          <v-list-item @click="openDetail(cr)">
            <template #prepend>
              <v-avatar :color="CHANGE_STATUS_COLORS[cr.status]" variant="tonal">
                <v-icon :icon="CHANGE_ACTION_ICONS[cr.action]" />
              </v-avatar>
            </template>
            <v-list-item-title class="font-weight-medium">
              {{ CHANGE_ACTION_LABELS[cr.action] }}
              <span v-if="cr.item_name">· {{ cr.item_name }}</span>
              <span v-else-if="cr.item_type">· {{ $t('cr.newOfType', { type: TYPE_LABELS[cr.item_type] }) }}</span>
            </v-list-item-title>
            <v-list-item-subtitle>{{ cr.description }}</v-list-item-subtitle>
            <template #append>
              <div class="d-flex flex-column align-end gap-1">
                <v-chip :color="CHANGE_STATUS_COLORS[cr.status]" size="small" variant="flat">
                  {{ $t('enums.changeStatus.' + cr.status) }}
                </v-chip>
                <span class="text-caption text-medium-emphasis">
                  {{ cr.proposer?.full_name }} · {{ timeAgo(cr.created_at) }}
                </span>
              </div>
            </template>
          </v-list-item>
          <v-divider v-if="i < requests.length - 1" />
        </template>
      </v-list>
      <EmptyState
        v-else
        icon="mdi-file-swap-outline"
        :title="$t('cr.empty')"
        :text="$t('cr.emptyHint')"
      />
    </v-card>

    <!-- Detail dialog -->
    <v-dialog v-model="detailOpen" max-width="640" scrollable>
      <v-card v-if="selected" rounded="lg">
        <v-card-title class="d-flex align-center gap-2 pa-4">
          <v-icon :icon="CHANGE_ACTION_ICONS[selected.action]" color="primary" />
          <span class="text-h6">{{ $t('cr.requestTitle', { action: CHANGE_ACTION_LABELS[selected.action] }) }}</span>
          <v-spacer />
          <v-chip :color="CHANGE_STATUS_COLORS[selected.status]" variant="flat">
            {{ $t('enums.changeStatus.' + selected.status) }}
          </v-chip>
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4" style="max-height: 62vh">
          <div class="d-flex flex-wrap gap-6 mb-4">
            <div>
              <div class="text-caption text-medium-emphasis">{{ $t('cr.proposedBy') }}</div>
              <div class="font-weight-medium">{{ selected.proposer?.full_name || '—' }}</div>
            </div>
            <div>
              <div class="text-caption text-medium-emphasis">{{ $t('cr.target') }}</div>
              <div class="font-weight-medium">
                <a
                  v-if="selected.item_id"
                  href="#"
                  @click.prevent="router.push(`/items/${selected.item_id}`)"
                >
                  {{ selected.item_name }}
                </a>
                <span v-else>{{ selected.item_type ? TYPE_LABELS[selected.item_type] : '—' }}</span>
              </div>
            </div>
            <div>
              <div class="text-caption text-medium-emphasis">{{ $t('cr.submitted') }}</div>
              <div class="font-weight-medium">{{ formatDateTime(selected.created_at) }}</div>
            </div>
          </div>

          <v-alert variant="tonal" color="primary" density="comfortable" class="mb-3">
            <div class="text-caption text-medium-emphasis">{{ $t('common.description') }}</div>
            <div>{{ selected.description }}</div>
            <div class="text-caption text-medium-emphasis mt-2">{{ $t('common.reason') }}</div>
            <div>{{ selected.reason }}</div>
          </v-alert>

          <div v-if="payloadRows.length" class="mb-2">
            <div class="text-overline text-medium-emphasis">{{ $t('cr.payload') }}</div>
            <v-table density="compact" class="border rounded">
              <tbody>
                <tr v-for="row in payloadRows" :key="row.key">
                  <td class="text-medium-emphasis" style="width: 40%">{{ row.key }}</td>
                  <td class="font-weight-medium">{{ row.value }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>

          <v-alert
            v-if="selected.status !== 'pending'"
            :color="selected.status === 'approved' ? 'success' : 'error'"
            variant="tonal"
            density="comfortable"
            class="mt-3"
          >
            <div class="text-caption">
              {{ $t('enums.changeStatus.' + selected.status) }} {{ $t('cr.by') }}
              {{ selected.reviewer?.full_name || '—' }} · {{ formatDateTime(selected.reviewed_at) }}
            </div>
            <div v-if="selected.review_note" class="mt-1">{{ selected.review_note }}</div>
          </v-alert>

          <v-textarea
            v-if="auth.isManager && selected.status === 'pending'"
            v-model="reviewNote"
            :label="$t('cr.reviewNote')"
            rows="2"
            auto-grow
            class="mt-4"
          />
        </v-card-text>

        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="detailOpen = false">{{ $t('common.close') }}</v-btn>
          <template v-if="auth.isManager && selected.status === 'pending'">
            <v-btn
              color="error"
              variant="tonal"
              prepend-icon="mdi-close"
              :loading="reviewing"
              @click="review('reject')"
            >
              {{ $t('cr.reject') }}
            </v-btn>
            <v-btn
              color="success"
              variant="flat"
              prepend-icon="mdi-check"
              :loading="reviewing"
              @click="review('approve')"
            >
              {{ $t('cr.approve') }}
            </v-btn>
          </template>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
