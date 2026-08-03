<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useNotificationsStore } from '@/stores/notifications'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { CARD_TYPE_LABELS, timeAgo } from '@/constants'
import type { LowStockComponent, NotificationItem } from '@/api/types'

const store = useNotificationsStore()
const ui = useUiStore()
const router = useRouter()
const { t } = useI18n({ useScope: 'global' })

const unreadOnly = ref(false)

const typeMeta: Record<string, { icon: string; color: string }> = {
  'change_request.submitted': { icon: 'mdi-file-plus-outline', color: 'amber-darken-2' },
  'change_request.approved': { icon: 'mdi-check-decagram', color: 'success' },
  'change_request.rejected': { icon: 'mdi-close-circle', color: 'error' },
  'inventory.low_stock': { icon: 'mdi-alert-decagram', color: 'orange-darken-3' },
  'item.state_changed': { icon: 'mdi-swap-horizontal', color: 'primary' },
}

function meta(type: string) {
  return typeMeta[type] ?? { icon: 'mdi-bell-outline', color: 'primary' }
}

/** The structured component list a low-stock alert carries, if it has one.
 *  Older notifications predate the payload and still render as plain text. */
function components(n: NotificationItem): LowStockComponent[] {
  return n.payload?.components ?? []
}

const shown = computed(() =>
  unreadOnly.value ? store.items.filter((n) => !n.read) : store.items,
)

async function refresh() {
  try {
    await store.fetchList(false)
    await store.fetchUnreadCount()
  } catch (e) {
    ui.error(e)
  }
}

async function open(n: NotificationItem) {
  if (!n.read) {
    try {
      await store.markRead(n.id)
    } catch (e) {
      ui.error(e)
    }
  }
  if (n.link) {
    // Links from the backend are app-relative paths (e.g. /items/12).
    router.push(n.link)
  }
}

/** Open the card the threshold was created from (or inventory as a fallback). */
async function openComponent(n: NotificationItem, c: LowStockComponent) {
  if (!n.read) {
    try {
      await store.markRead(n.id)
    } catch (e) {
      ui.error(e)
    }
  }
  router.push(c.link || '/inventory')
}

async function markAll() {
  try {
    await store.markAllRead()
    ui.success(t('notif.markAllToast'))
  } catch (e) {
    ui.error(e)
  }
}

onMounted(refresh)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader
      :title="$t('nav.notifications')"
      :subtitle="$t('notif.subtitle')"
      icon="mdi-bell-outline"
    >
      <template #actions>
        <v-switch
          v-model="unreadOnly"
          :label="$t('notif.unreadOnly')"
          color="primary"
          hide-details
          density="comfortable"
          class="me-2"
        />
        <v-btn
          variant="tonal"
          prepend-icon="mdi-email-open-outline"
          :disabled="store.unread === 0"
          @click="markAll"
        >
          {{ $t('notif.markAll') }}
        </v-btn>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="store.loading" @click="refresh" />
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <div v-if="store.loading && !store.items.length" class="pa-4">
        <v-skeleton-loader type="list-item-two-line@6" />
      </div>
      <v-list v-else-if="shown.length" lines="two">
        <template v-for="(n, i) in shown" :key="n.id">
          <v-list-item
            :class="{ 'bg-surface-variant': !n.read }"
            @click="open(n)"
          >
            <template #prepend>
              <v-badge :model-value="!n.read" color="primary" dot location="top start">
                <v-avatar :color="meta(n.type).color" variant="tonal">
                  <v-icon :icon="meta(n.type).icon" />
                </v-avatar>
              </v-badge>
            </template>
            <v-list-item-title class="font-weight-medium">{{ n.title }}</v-list-item-title>
            <!-- A low-stock alert carries its components as data, so it renders
                 as the list of what is actually short rather than a paragraph
                 the reader has to parse. -->
            <template v-if="components(n).length">
              <div class="low-stock-list mt-2 mb-1">
                <div
                  v-for="c in components(n)"
                  :key="c.threshold_id ?? c.name"
                  class="low-stock-row"
                  :class="{ 'low-stock-row--link': !!c.item_id }"
                  @click.stop="openComponent(n, c)"
                >
                  <v-icon icon="mdi-memory" size="16" class="me-2 text-medium-emphasis" />
                  <!-- The threshold was set on a real card, so the row opens it
                       instead of leaving the reader to search for the name. -->
                  <span class="font-weight-medium">{{ c.name }}</span>
                  <span v-if="c.version" class="text-medium-emphasis ms-1">v{{ c.version }}</span>
                  <v-chip size="x-small" variant="tonal" class="ms-2">
                    {{ CARD_TYPE_LABELS[c.card_type] }}
                  </v-chip>
                  <v-spacer />
                  <span class="text-error font-weight-bold">{{ c.current_quantity }}</span>
                  <span class="text-medium-emphasis mx-1">/</span>
                  <span class="text-medium-emphasis">{{ c.min_quantity }}</span>
                  <v-chip size="x-small" color="warning" variant="tonal" class="ms-2">
                    {{ $t('notif.lowStock.short', { n: c.shortfall }) }}
                  </v-chip>
                </div>
              </div>
              <v-list-item-subtitle>
                {{ $t('notif.lowStock.hint') }}
              </v-list-item-subtitle>
            </template>
            <v-list-item-subtitle v-else>{{ n.body }}</v-list-item-subtitle>
            <template #append>
              <div class="d-flex align-center gap-2">
                <span class="text-caption text-medium-emphasis">{{ timeAgo(n.created_at) }}</span>
                <v-btn
                  v-if="!n.read"
                  icon="mdi-check"
                  size="x-small"
                  variant="text"
                  @click.stop="store.markRead(n.id)"
                />
              </div>
            </template>
          </v-list-item>
          <v-divider v-if="i < shown.length - 1" />
        </template>
      </v-list>
      <EmptyState
        v-else
        icon="mdi-bell-check-outline"
        :title="$t('notif.allCaught')"
        :text="$t('notif.allCaughtHint')"
      />
    </v-card>
  </v-container>
</template>

<style scoped>
.low-stock-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.low-stock-row--link {
  cursor: pointer;
  border-radius: 4px;
}

.low-stock-row--link:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.low-stock-row {
  display: flex;
  align-items: center;
  font-size: 0.875rem;
  /* The rows are a table of numbers; let them scroll rather than squash the
     quantity against the minimum on a narrow screen. */
  min-width: 0;
  white-space: nowrap;
  overflow-x: auto;
}
</style>
