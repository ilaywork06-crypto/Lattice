<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { itemsApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import TypeIcon from '@/components/TypeIcon.vue'
import ItemFormDialog from '@/components/ItemFormDialog.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import { TYPE_LABELS, ITEM_TYPES } from '@/constants'
import type { ItemCreate, ItemListOut, ItemType, ItemUpdate } from '@/api/types'

const { t } = useI18n({ useScope: 'global' })
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()

const templates = ref<ItemListOut[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    templates.value = await itemsApi.list({ templates: true, limit: 500 })
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

const grouped = computed(() =>
  ITEM_TYPES.map((ty) => ({
    type: ty,
    items: templates.value.filter((i) => i.type === ty),
  })).filter((g) => g.items.length),
)

// ---- New template ---------------------------------------------------------
const newOpen = ref(false)
const newType = ref<ItemType>('card')

function startNewTemplate(ty: ItemType) {
  newType.value = ty
  newOpen.value = true
}

async function onNewTemplate(payload: ItemCreate | ItemUpdate) {
  try {
    await itemsApi.create(payload as ItemCreate)
    ui.success(t('templates.created'))
    newOpen.value = false
    await load()
  } catch (e) {
    ui.error(e)
  }
}

// ---- New item from template ----------------------------------------------
const fromOpen = ref(false)
const fromType = ref<ItemType>('card')
const fromPrefill = ref<Partial<ItemCreate> | null>(null)

async function useTemplate(tpl: ItemListOut) {
  try {
    const full = await itemsApi.get(tpl.id)
    fromType.value = full.type
    fromPrefill.value = {
      name: full.name,
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
      // a serialised card needs its own serial; a commercial one inherits the
      // template's quantity as a starting point
      serial: null,
      quantity: full.quantity,
      manager_ids: full.managers.map((m) => m.id),
    }
    fromOpen.value = true
  } catch (e) {
    ui.error(e)
  }
}

async function onCreateFromTemplate(payload: ItemCreate | ItemUpdate) {
  try {
    const created = await itemsApi.create(payload as ItemCreate)
    ui.success(t('templates.instantiated'))
    fromOpen.value = false
    router.push(`/items/${created.id}`)
  } catch (e) {
    ui.error(e)
  }
}

// ---- Delete ---------------------------------------------------------------
const removeTpl = ref<ItemListOut | null>(null)
async function confirmRemove() {
  if (!removeTpl.value) return
  try {
    await itemsApi.remove(removeTpl.value.id)
    ui.success(t('templates.deleted'))
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    removeTpl.value = null
  }
}

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader :title="$t('nav.templates')" :subtitle="$t('templates.subtitle')" icon="mdi-content-duplicate">
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="load" />
        <v-menu location="bottom end">
          <template #activator="{ props }">
            <v-btn v-bind="props" color="primary" prepend-icon="mdi-plus" append-icon="mdi-menu-down">
              {{ $t('templates.new') }}
            </v-btn>
          </template>
          <v-list density="compact" nav>
            <v-list-item
              v-for="ty in ITEM_TYPES"
              :key="ty"
              :title="$t('templates.newOf', { type: TYPE_LABELS[ty] })"
              @click="startNewTemplate(ty)"
            >
              <template #prepend><TypeIcon :type="ty" :size="20" /></template>
            </v-list-item>
          </v-list>
        </v-menu>
      </template>
    </PageHeader>

    <v-skeleton-loader v-if="loading && !templates.length" type="card@2" />

    <template v-else-if="grouped.length">
      <div v-for="group in grouped" :key="group.type" class="mb-6">
        <div class="d-flex align-center gap-2 mb-3">
          <TypeIcon :type="group.type" :size="22" />
          <span class="text-subtitle-1 font-weight-bold">{{ TYPE_LABELS[group.type] }}</span>
          <v-chip size="x-small" variant="tonal">{{ group.items.length }}</v-chip>
        </div>
        <v-row dense>
          <v-col v-for="tpl in group.items" :key="tpl.id" cols="12" sm="6" md="4">
            <v-card variant="flat" border height="100%" class="d-flex flex-column">
              <v-card-item>
                <template #prepend>
                  <v-avatar color="deep-purple" variant="tonal" rounded="lg">
                    <TypeIcon :type="tpl.type" :size="22" />
                  </v-avatar>
                </template>
                <v-card-title class="text-body-1 font-weight-bold">{{ tpl.name }}</v-card-title>
                <v-card-subtitle>
                  <span v-if="tpl.project">{{ tpl.project }}</span>
                  <span v-if="tpl.project && tpl.industry"> · </span>
                  <span v-if="tpl.industry">{{ tpl.industry }}</span>
                  <span v-if="!tpl.project && !tpl.industry">—</span>
                </v-card-subtitle>
              </v-card-item>
              <v-spacer />
              <v-card-actions class="px-4 pb-3">
                <v-btn
                  color="primary"
                  variant="tonal"
                  size="small"
                  prepend-icon="mdi-plus"
                  @click="useTemplate(tpl)"
                >
                  {{ $t('templates.use') }}
                </v-btn>
                <v-spacer />
                <v-btn size="small" variant="text" icon="mdi-open-in-new" @click="router.push(`/items/${tpl.id}`)" />
                <v-btn
                  v-if="auth.canDirectEdit"
                  size="small"
                  variant="text"
                  color="error"
                  icon="mdi-delete-outline"
                  @click="removeTpl = tpl"
                />
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>
      </div>
    </template>

    <EmptyState
      v-else
      icon="mdi-content-duplicate"
      :title="$t('templates.empty')"
      :text="$t('templates.emptyHint')"
    />

    <ItemFormDialog
      v-model="newOpen"
      mode="create"
      :type="newType"
      as-template
      :direct="auth.canDirectEdit"
      @submit="onNewTemplate"
    />
    <ItemFormDialog
      v-model="fromOpen"
      mode="create"
      :type="fromType"
      :prefill="fromPrefill"
      :direct="auth.canDirectEdit"
      @submit="onCreateFromTemplate"
    />
    <ConfirmDialog
      :model-value="removeTpl !== null"
      :title="$t('templates.deleteTitle')"
      :message="removeTpl ? $t('templates.deleteMsg', { name: removeTpl.name }) : ''"
      :confirm-text="$t('common.delete')"
      color="error"
      @update:model-value="(v) => !v && (removeTpl = null)"
      @confirm="confirmRemove"
    />
  </v-container>
</template>
