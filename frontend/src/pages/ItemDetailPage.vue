<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { auditApi, itemsApi, usersApi } from '@/api/services'
import { extractError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import StateChip from '@/components/StateChip.vue'
import TypeIcon from '@/components/TypeIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import ItemFormDialog from '@/components/ItemFormDialog.vue'
import ProposeChangeDialog from '@/components/ProposeChangeDialog.vue'
import type { ProposeContext } from '@/lib/propose'
import MoveDialog from '@/components/dialogs/MoveDialog.vue'
import StateDialog from '@/components/dialogs/StateDialog.vue'
import LinkDialog from '@/components/dialogs/LinkDialog.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import {
  CARD_TYPE_LABELS,
  STATE_COLORS,
  STATE_LABELS,
  STORAGE_COLORS,
  STORAGE_LABELS,
  TYPE_LABELS,
  formatDate,
  formatDateTime,
  isQuantityTracked,
} from '@/constants'
import type {
  AuditOut,
  ItemCreate,
  ItemListOut,
  ItemOut,
  ItemType,
  ItemUpdate,
  UserBrief,
} from '@/api/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

// Where "back" goes.
//
// History is the wrong tool for this button. The item page is reachable from the
// dashboard, global search, the graph, a notification link and a plain bookmark,
// and `router.back()` honours none of that: from a freshly opened tab it walks
// out of the app entirely (verified: it lands on about:blank), and with no entry
// to pop it does nothing at all — the button just looks broken. A destination
// derived from the item is correct from every entry point and never dead.
const LIST_ROUTE: Record<ItemOut['type'], { to: string; label: string }> = {
  setup: { to: '/setups', label: 'nav.setups' },
  assembly: { to: '/assemblies', label: 'nav.assemblies' },
  card: { to: '/cards', label: 'nav.cards' },
}

const backTarget = computed(() => {
  const it = item.value
  if (!it) return { to: '/', label: t('nav.dashboard') }
  if (it.is_template) return { to: '/templates', label: t('nav.templates') }
  const r = LIST_ROUTE[it.type]
  return { to: r.to, label: t(r.label) }
})

function goBack() {
  router.push(backTarget.value.to)
}

const itemId = computed(() => Number(route.params.id))
const item = ref<ItemOut | null>(null)
const loading = ref(true)
const tab = ref('overview')

const audit = ref<AuditOut[]>([])
const auditLoaded = ref(false)

async function loadItem() {
  loading.value = true
  try {
    item.value = await itemsApi.get(itemId.value)
  } catch (e) {
    ui.error(e)
    item.value = null
  } finally {
    loading.value = false
  }
}

async function loadAudit() {
  if (auditLoaded.value) return
  try {
    audit.value = await auditApi.list({ item_id: itemId.value, limit: 100 })
    auditLoaded.value = true
  } catch (e) {
    ui.error(e)
  }
}

watch(tab, (t) => {
  if (t === 'audit') void loadAudit()
})

watch(itemId, () => {
  auditLoaded.value = false
  tab.value = 'overview'
  void loadItem()
})

// ---------------------------------------------------------------------------
// Contents (what sits inside this container)
// ---------------------------------------------------------------------------
// Contents could only be chosen while *creating* a setup or assembly, so a
// container put together wrongly could never be corrected. This edits it in
// place: the dialog submits the full membership and the server links/unlinks
// the difference, cascading locations exactly as a normal link would.
const CONTENT_TYPES: Record<ItemType, ItemType[]> = {
  setup: ['assembly', 'card'],
  assembly: ['card'],
  card: [],
}

const contentsOpen = ref(false)
const contentsSaving = ref(false)
const contentsIds = ref<number[]>([])
const contentsOptions = ref<ItemListOut[]>([])
const contentsLoading = ref(false)

const contentsSelectItems = computed(() =>
  contentsOptions.value.map((c) => ({
    value: c.id,
    title: c.name,
    subtitle:
      c.parent_id && c.parent_id !== item.value?.id
        ? `${TYPE_LABELS[c.type]} · ${t('itemForm.willMove')}`
        : TYPE_LABELS[c.type],
  })),
)

async function openContents() {
  if (!item.value) return
  actionError.value = ''
  contentsIds.value = item.value.children.map((c) => c.id)
  contentsOpen.value = true
  contentsLoading.value = true
  try {
    const lists = await Promise.all(
      CONTENT_TYPES[item.value.type].map((ty) => itemsApi.list({ type: ty, limit: 500 })),
    )
    contentsOptions.value = lists
      .flat()
      .filter((c) => c.id !== item.value?.id)
      // free items first, then ones that would be re-homed from another container
      .sort(
        (a, b) =>
          Number(!!a.parent_id) - Number(!!b.parent_id) || a.name.localeCompare(b.name),
      )
  } catch (e) {
    ui.error(e)
  } finally {
    contentsLoading.value = false
  }
}

async function saveContents() {
  if (!item.value) return
  contentsSaving.value = true
  try {
    await itemsApi.setChildren(item.value.id, contentsIds.value)
    ui.success(t('detail.contentsUpdated'))
    contentsOpen.value = false
    await loadItem()
  } catch (e) {
    ui.error(e)
  } finally {
    contentsSaving.value = false
  }
}

// ---------------------------------------------------------------------------
// Overview fields
// ---------------------------------------------------------------------------
const overviewFields = computed(() => {
  const it = item.value
  if (!it) return []
  const rows: { label: string; value: string; icon?: string }[] = [
    { label: t('fields.industry'), value: it.industry || '—', icon: 'mdi-factory' },
    { label: t('fields.project'), value: it.project || '—', icon: 'mdi-folder-outline' },
    { label: t('fields.team'), value: it.team || '—', icon: 'mdi-account-group-outline' },
    { label: t('fields.dmz'), value: it.dmz || '—', icon: 'mdi-shield-outline' },
  ]
  if (it.type === 'card') {
    rows.push(
      { label: t('fields.responsible'), value: it.responsible || '—', icon: 'mdi-account' },
      { label: t('fields.lead'), value: it.lead || '—', icon: 'mdi-account-star' },
      { label: t('fields.version'), value: it.version || '—', icon: 'mdi-tag-outline' },
      // Only one of the two applies — showing the other as "—" is what made the
      // two kinds of card look like the same thing with missing data.
      isQuantityTracked(it.card_type)
        ? { label: t('fields.quantity'), value: String(it.quantity ?? 1), icon: 'mdi-numeric' }
        : { label: t('fields.serial'), value: it.serial || '—', icon: 'mdi-barcode' },
      { label: t('fields.productionDate'), value: formatDate(it.production_date), icon: 'mdi-calendar' },
    )
  }
  rows.push(
    { label: t('fields.createdAt'), value: formatDateTime(it.created_at), icon: 'mdi-clock-plus-outline' },
    { label: t('fields.updatedAt'), value: formatDateTime(it.updated_at), icon: 'mdi-clock-edit-outline' },
  )
  return rows
})

const tabs = computed(() => {
  const base = [
    { value: 'overview', label: t('items.tabs.overview'), icon: 'mdi-information-outline' },
    { value: 'hierarchy', label: t('items.tabs.hierarchy'), icon: 'mdi-file-tree-outline' },
    { value: 'history', label: t('items.tabs.stateHistory'), icon: 'mdi-history' },
  ]
  if (item.value?.type === 'card') {
    base.push({ value: 'documents', label: t('items.tabs.documents'), icon: 'mdi-file-document-outline' })
  }
  if (item.value?.type === 'setup') {
    base.push({ value: 'extras', label: t('items.tabs.extras'), icon: 'mdi-package-variant-closed' })
  }
  base.push(
    { value: 'managers', label: t('items.tabs.managers'), icon: 'mdi-account-tie' },
    { value: 'audit', label: t('items.tabs.audit'), icon: 'mdi-clipboard-text-clock-outline' },
  )
  return base
})

// ---------------------------------------------------------------------------
// Actions — direct (manager) vs propose (editor)
// ---------------------------------------------------------------------------
const editOpen = ref(false)
const moveOpen = ref(false)
const stateOpen = ref(false)
const linkOpen = ref(false)
const unlinkOpen = ref(false)
const deleteOpen = ref(false)

const proposeOpen = ref(false)
const proposeCtx = ref<ProposeContext | null>(null)

const actionError = ref('')
const actionLoading = ref(false)

function openPropose(ctx: ProposeContext) {
  proposeCtx.value = ctx
  proposeOpen.value = true
}

// Edit ----------------------------------------------------------------------
async function onEditSubmit(payload: ItemCreate | ItemUpdate) {
  if (!item.value) return
  if (auth.canDirectEdit) {
    try {
      item.value = await itemsApi.update(item.value.id, payload as ItemUpdate)
      ui.success(t('detail.updated'))
      editOpen.value = false
    } catch (e) {
      ui.error(e)
    }
  } else {
    editOpen.value = false
    openPropose({
      action: 'update',
      itemId: item.value.id,
      itemType: item.value.type,
      payload: payload as Record<string, unknown>,
      targetName: item.value.name,
      summaryLines: [{ label: t('fields.name'), value: (payload as ItemUpdate).name ?? item.value.name }],
    })
  }
}

// Move ----------------------------------------------------------------------
async function onMoveConfirm(payload: { location_id: number; note?: string }) {
  if (!item.value) return
  actionError.value = ''
  if (auth.canDirectEdit) {
    actionLoading.value = true
    try {
      item.value = await itemsApi.move(item.value.id, payload.location_id, payload.note)
      ui.success(t('detail.moved'))
      moveOpen.value = false
    } catch (e) {
      actionError.value = extractError(e)
    } finally {
      actionLoading.value = false
    }
  } else {
    moveOpen.value = false
    openPropose({
      action: 'move',
      itemId: item.value.id,
      itemType: item.value.type,
      payload,
      targetName: item.value.name,
    })
  }
}

// State ---------------------------------------------------------------------
async function onStateConfirm(payload: { state: ItemOut['state']; note?: string }) {
  if (!item.value) return
  actionError.value = ''
  if (auth.canDirectEdit) {
    actionLoading.value = true
    try {
      item.value = await itemsApi.changeState(item.value.id, payload.state, payload.note)
      auditLoaded.value = false
      ui.success(t('detail.stateUpdated'))
      stateOpen.value = false
    } catch (e) {
      actionError.value = extractError(e)
    } finally {
      actionLoading.value = false
    }
  } else {
    stateOpen.value = false
    openPropose({
      action: 'state_change',
      itemId: item.value.id,
      itemType: item.value.type,
      payload,
      targetName: item.value.name,
      summaryLines: [{ label: t('detail.newState'), value: STATE_LABELS[payload.state] }],
    })
  }
}

// Link ----------------------------------------------------------------------
async function onLinkConfirm(payload: { parent_id: number }) {
  if (!item.value) return
  actionError.value = ''
  if (auth.canDirectEdit) {
    actionLoading.value = true
    try {
      item.value = await itemsApi.link(item.value.id, payload.parent_id)
      ui.success(t('detail.linked'))
      linkOpen.value = false
    } catch (e) {
      actionError.value = extractError(e)
    } finally {
      actionLoading.value = false
    }
  } else {
    linkOpen.value = false
    openPropose({
      action: 'link',
      itemId: item.value.id,
      itemType: item.value.type,
      payload,
      targetName: item.value.name,
    })
  }
}

// Unlink --------------------------------------------------------------------
async function onUnlinkConfirm() {
  if (!item.value) return
  actionError.value = ''
  if (auth.canDirectEdit) {
    actionLoading.value = true
    try {
      item.value = await itemsApi.unlink(item.value.id)
      ui.success(t('detail.unlinked'))
      unlinkOpen.value = false
    } catch (e) {
      actionError.value = extractError(e)
    } finally {
      actionLoading.value = false
    }
  } else {
    unlinkOpen.value = false
    openPropose({
      action: 'unlink',
      itemId: item.value.id,
      itemType: item.value.type,
      payload: {},
      targetName: item.value.name,
    })
  }
}

// Delete --------------------------------------------------------------------
async function onDeleteConfirm() {
  if (!item.value) return
  actionError.value = ''
  if (auth.canDirectEdit) {
    actionLoading.value = true
    try {
      const target = backTarget.value.to
      await itemsApi.remove(item.value.id)
      ui.success(t('detail.deleted'))
      deleteOpen.value = false
      // replace, not push/back: the deleted item's URL must not stay reachable
      // through the Forward button, where it would 404.
      router.replace(target)
    } catch (e) {
      actionError.value = extractError(e)
    } finally {
      actionLoading.value = false
    }
  } else {
    deleteOpen.value = false
    openPropose({
      action: 'delete',
      itemId: item.value.id,
      itemType: item.value.type,
      payload: {},
      targetName: item.value.name,
    })
  }
}

// ---------------------------------------------------------------------------
// Duplicate / Save as template (§5 convenience)
// ---------------------------------------------------------------------------
const createOpen = ref(false)
const createPrefill = ref<Partial<ItemCreate> | null>(null)
const createAsTemplate = ref(false)

function prefillFromItem(): Partial<ItemCreate> {
  const it = item.value!
  return {
    name: it.name,
    industry: it.industry,
    project: it.project,
    team: it.team,
    state: it.state,
    description: it.description,
    dmz: it.dmz,
    location_id: it.location_id,
    card_type: it.card_type,
    responsible: it.responsible,
    lead: it.lead,
    version: it.version,
    storage_status: it.storage_status,
    serial: null, // a copy must get its own serial
    quantity: 1, // ...and a copy of a commercial card starts at a single unit
    manager_ids: it.managers.map((m) => m.id),
  }
}

function openDuplicate() {
  if (!item.value) return
  createAsTemplate.value = false
  createPrefill.value = {
    ...prefillFromItem(),
    name: item.value.is_template ? item.value.name : `${item.value.name} ${t('items.copySuffix')}`,
  }
  createOpen.value = true
}

function openSaveAsTemplate() {
  if (!item.value) return
  createAsTemplate.value = true
  createPrefill.value = prefillFromItem()
  createOpen.value = true
}

async function onCreateSubmit(payload: ItemCreate | ItemUpdate) {
  if (!item.value) return
  if (auth.canDirectEdit) {
    try {
      const created = await itemsApi.create(payload as ItemCreate)
      ui.success(createAsTemplate.value ? t('detail.templateSaved') : t('detail.duplicated'))
      createOpen.value = false
      router.push(`/items/${created.id}`)
    } catch (e) {
      ui.error(e)
    }
  } else {
    createOpen.value = false
    openPropose({
      action: 'create',
      itemType: item.value.type,
      payload: payload as Record<string, unknown>,
      targetName: (payload as ItemCreate).name,
      summaryLines: [{ label: t('fields.name'), value: (payload as ItemCreate).name }],
    })
  }
}

// ---------------------------------------------------------------------------
// Documents (cards, manager only)
// ---------------------------------------------------------------------------
const docOpen = ref(false)
const docForm = reactive({ name: '', url: '', doc_type: '' })
const docSaving = ref(false)
const removeDocId = ref<number | null>(null)

function openDocDialog() {
  docForm.name = ''
  docForm.url = ''
  docForm.doc_type = ''
  docOpen.value = true
}
async function addDocument() {
  if (!item.value || !docForm.name.trim()) return
  docSaving.value = true
  try {
    await itemsApi.addDocument(item.value.id, {
      name: docForm.name.trim(),
      url: docForm.url.trim() || undefined,
      doc_type: docForm.doc_type.trim() || undefined,
    })
    await loadItem()
    ui.success(t('detail.docAdded'))
    docOpen.value = false
  } catch (e) {
    ui.error(e)
  } finally {
    docSaving.value = false
  }
}
async function confirmRemoveDoc() {
  if (!item.value || removeDocId.value == null) return
  try {
    await itemsApi.removeDocument(item.value.id, removeDocId.value)
    await loadItem()
    ui.success(t('detail.docRemoved'))
  } catch (e) {
    ui.error(e)
  } finally {
    removeDocId.value = null
  }
}

// ---------------------------------------------------------------------------
// Extra items (setups, manager only)
// ---------------------------------------------------------------------------
const extraOpen = ref(false)
const extraForm = reactive({ name: '', company_part_number: '', serial: '', signed_by: '' })
const extraSaving = ref(false)
const removeExtraId = ref<number | null>(null)

function openExtraDialog() {
  extraForm.name = ''
  extraForm.company_part_number = ''
  extraForm.serial = ''
  extraForm.signed_by = ''
  extraOpen.value = true
}
async function addExtra() {
  if (!item.value || !extraForm.name.trim()) return
  extraSaving.value = true
  try {
    await itemsApi.addExtra(item.value.id, {
      name: extraForm.name.trim(),
      company_part_number: extraForm.company_part_number.trim() || undefined,
      serial: extraForm.serial.trim() || undefined,
      signed_by: extraForm.signed_by.trim() || undefined,
    })
    await loadItem()
    ui.success(t('detail.extraAdded'))
    extraOpen.value = false
  } catch (e) {
    ui.error(e)
  } finally {
    extraSaving.value = false
  }
}
async function confirmRemoveExtra() {
  if (!item.value || removeExtraId.value == null) return
  try {
    await itemsApi.removeExtra(item.value.id, removeExtraId.value)
    await loadItem()
    ui.success(t('detail.extraRemoved'))
  } catch (e) {
    ui.error(e)
  } finally {
    removeExtraId.value = null
  }
}

// ---------------------------------------------------------------------------
// Managers (edit manager_ids: direct or propose)
// ---------------------------------------------------------------------------
const managersOpen = ref(false)
const managerOptions = ref<UserBrief[]>([])
const selectedManagerIds = ref<number[]>([])
const managersSaving = ref(false)

async function openManagersDialog() {
  if (!item.value) return
  selectedManagerIds.value = item.value.managers.map((m) => m.id)
  managersOpen.value = true
  try {
    managerOptions.value = await usersApi.managers()
  } catch (e) {
    ui.error(e)
  }
}
async function saveManagers() {
  if (!item.value) return
  managersSaving.value = true
  const payload = { manager_ids: selectedManagerIds.value }
  try {
    if (auth.canDirectEdit) {
      item.value = await itemsApi.update(item.value.id, payload)
      ui.success(t('detail.managersUpdated'))
      managersOpen.value = false
    } else {
      managersOpen.value = false
      openPropose({
        action: 'update',
        itemId: item.value.id,
        itemType: item.value.type,
        payload,
        targetName: item.value.name,
        summaryLines: [
          {
            label: t('fields.managers'),
            value:
              managerOptions.value
                .filter((m) => selectedManagerIds.value.includes(m.id))
                .map((m) => m.full_name)
                .join(', ') || t('common.none'),
          },
        ],
      })
    }
  } catch (e) {
    ui.error(e)
  } finally {
    managersSaving.value = false
  }
}

onMounted(loadItem)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <v-btn variant="text" prepend-icon="mdi-arrow-left" class="mb-3 flip-rtl-icon" @click="goBack">
      {{ $t('detail.backTo', { target: backTarget.label }) }}
    </v-btn>

    <v-skeleton-loader v-if="loading" type="article, list-item-three-line@3" />

    <template v-else-if="item">
      <!-- Header -->
      <v-card variant="flat" border class="mb-4">
        <v-card-text class="pa-5">
          <div class="d-flex flex-wrap align-center justify-space-between gap-4">
            <div class="d-flex align-center gap-4">
              <v-avatar
                :color="STATE_COLORS[item.state]"
                variant="tonal"
                rounded="lg"
                size="60"
              >
                <TypeIcon :type="item.type" :size="30" />
              </v-avatar>
              <div>
                <div class="d-flex align-center gap-2 flex-wrap">
                  <h1 class="text-h5 font-weight-bold">{{ item.name }}</h1>
                  <StateChip :state="item.state" />
                  <v-chip
                    v-if="item.is_template"
                    color="deep-purple"
                    size="small"
                    variant="flat"
                    prepend-icon="mdi-shape-square-plus"
                  >
                    {{ $t('detail.templateBadge') }}
                  </v-chip>
                </div>
                <div class="text-body-2 text-medium-emphasis mt-1 d-flex align-center flex-wrap gap-3">
                  <span>
                    <v-icon icon="mdi-shape-outline" size="14" /> {{ TYPE_LABELS[item.type] }}
                  </span>
                  <span v-if="item.card_type">
                    <v-icon icon="mdi-card-outline" size="14" />
                    {{ CARD_TYPE_LABELS[item.card_type] }}
                  </span>
                  <span v-if="item.location">
                    <v-icon icon="mdi-map-marker" size="14" /> {{ item.location.name }}
                  </span>
                  <v-chip
                    v-if="item.storage_status"
                    :color="STORAGE_COLORS[item.storage_status]"
                    size="x-small"
                    variant="tonal"
                  >
                    {{ STORAGE_LABELS[item.storage_status] }}
                  </v-chip>
                </div>
              </div>
            </div>

            <!-- Action buttons (role-guarded) -->
            <div v-if="auth.canPropose" class="d-flex align-center gap-2">
              <v-btn
                color="primary"
                variant="flat"
                prepend-icon="mdi-pencil"
                @click="editOpen = true"
              >
                {{ auth.canDirectEdit ? $t('detail.edit') : $t('detail.proposeEdit') }}
              </v-btn>
              <v-menu location="bottom end">
                <template #activator="{ props }">
                  <v-btn v-bind="props" variant="tonal" icon="mdi-dots-vertical" />
                </template>
                <v-list density="compact" nav>
                  <!-- A linked item is physically inside its parent, so it has
                       no location of its own to change (§3). -->
                  <v-list-item
                    prepend-icon="mdi-map-marker-radius"
                    :title="$t('items.actions.move')"
                    :disabled="!!item.parent"
                    :subtitle="item.parent ? $t('detail.moveLockedShort') : undefined"
                    @click="(actionError = ''), (moveOpen = true)"
                  />
                  <v-list-item
                    prepend-icon="mdi-swap-horizontal"
                    :title="$t('items.actions.changeState')"
                    @click="(actionError = ''), (stateOpen = true)"
                  />
                  <v-list-item
                    v-if="item.type !== 'setup'"
                    prepend-icon="mdi-link-variant"
                    :title="$t('items.actions.link')"
                    @click="(actionError = ''), (linkOpen = true)"
                  />
                  <v-list-item
                    v-if="item.parent"
                    prepend-icon="mdi-link-variant-off"
                    :title="$t('detail.unlinkFromParent')"
                    @click="(actionError = ''), (unlinkOpen = true)"
                  />
                  <v-divider class="my-1" />
                  <v-list-item
                    prepend-icon="mdi-content-duplicate"
                    :title="item.is_template ? $t('detail.newFromTemplate') : $t('items.actions.duplicate')"
                    @click="openDuplicate"
                  />
                  <v-list-item
                    v-if="!item.is_template"
                    prepend-icon="mdi-shape-square-plus"
                    :title="$t('detail.saveAsTemplate')"
                    @click="openSaveAsTemplate"
                  />
                  <v-divider class="my-1" />
                  <v-list-item
                    prepend-icon="mdi-delete"
                    :title="$t('common.delete')"
                    base-color="error"
                    @click="(actionError = ''), (deleteOpen = true)"
                  />
                </v-list>
              </v-menu>
            </div>
          </div>

          <p v-if="item.description" class="text-body-2 mt-4 mb-0">{{ item.description }}</p>
        </v-card-text>
      </v-card>

      <!-- Tabs -->
      <v-card variant="flat" border>
        <v-tabs v-model="tab" color="primary" show-arrows>
          <v-tab v-for="t in tabs" :key="t.value" :value="t.value" :prepend-icon="t.icon">
            {{ t.label }}
          </v-tab>
        </v-tabs>
        <v-divider />

        <v-window v-model="tab">
          <!-- Overview -->
          <v-window-item value="overview" class="pa-5">
            <v-row dense>
              <v-col v-for="f in overviewFields" :key="f.label" cols="12" sm="6" md="4">
                <div class="d-flex align-center gap-3 py-2">
                  <v-icon :icon="f.icon" size="20" class="text-medium-emphasis" />
                  <div>
                    <div class="text-caption text-medium-emphasis">{{ f.label }}</div>
                    <div class="text-body-2 font-weight-medium">{{ f.value }}</div>
                  </div>
                </div>
              </v-col>
            </v-row>
          </v-window-item>

          <!-- Hierarchy (bidirectional) -->
          <v-window-item value="hierarchy" class="pa-5">
            <v-alert
              v-if="item.parent"
              type="info"
              variant="tonal"
              density="compact"
              class="mb-4"
              icon="mdi-map-marker-off-outline"
            >
              <i18n-t keypath="detail.moveLocked" scope="global">
                <template #name><strong>{{ item.name }}</strong></template>
                <template #parent>
                  <RouterLink :to="`/items/${item.parent.id}`" class="text-primary">
                    {{ item.parent.name }}
                  </RouterLink>
                </template>
              </i18n-t>
            </v-alert>

            <div class="mb-5">
              <div class="text-overline text-medium-emphasis mb-2">{{ $t('detail.parent') }}</div>
              <v-card
                v-if="item.parent"
                variant="tonal"
                class="clickable-row"
                @click="router.push(`/items/${item.parent.id}`)"
              >
                <v-card-text class="d-flex align-center gap-3">
                  <TypeIcon :type="item.parent.type" :size="24" />
                  <div class="flex-grow-1">
                    <div class="font-weight-medium">{{ item.parent.name }}</div>
                    <div class="text-caption text-medium-emphasis">
                      {{ TYPE_LABELS[item.parent.type] }}
                    </div>
                  </div>
                  <StateChip :state="item.parent.state" />
                  <v-icon icon="mdi-chevron-right" class="flip-rtl" />
                </v-card-text>
              </v-card>
              <div v-else class="text-body-2 text-medium-emphasis">
                {{ $t('detail.noParent') }}
              </div>
            </div>

            <div>
              <div class="d-flex align-center gap-2 mb-2">
                <div class="text-overline text-medium-emphasis">
                  {{ $t('detail.children', { n: item.children.length }) }}
                </div>
                <v-spacer />
                <v-btn
                  v-if="auth.canDirectEdit && item.type !== 'card'"
                  size="small"
                  variant="tonal"
                  prepend-icon="mdi-playlist-edit"
                  @click="openContents"
                >
                  {{ $t('detail.editContents') }}
                </v-btn>
              </div>
              <v-row v-if="item.children.length" dense>
                <v-col v-for="child in item.children" :key="child.id" cols="12" sm="6" md="4">
                  <v-card
                    variant="outlined"
                    class="clickable-row"
                    @click="router.push(`/items/${child.id}`)"
                  >
                    <v-card-text class="d-flex align-center gap-3">
                      <TypeIcon :type="child.type" :size="22" />
                      <div class="flex-grow-1 overflow-hidden">
                        <div class="font-weight-medium text-truncate">{{ child.name }}</div>
                        <div class="text-caption text-medium-emphasis">
                          {{ TYPE_LABELS[child.type] }}
                        </div>
                      </div>
                      <StateChip :state="child.state" />
                    </v-card-text>
                  </v-card>
                </v-col>
              </v-row>
              <EmptyState
                v-else
                icon="mdi-file-tree-outline"
                :title="$t('detail.noChildren')"
                :text="$t('detail.noChildrenHint')"
              />
            </div>
          </v-window-item>

          <!-- State history -->
          <v-window-item value="history" class="pa-5">
            <v-timeline
              v-if="item.state_history.length"
              side="end"
              align="start"
              density="comfortable"
              truncate-line="both"
            >
              <v-timeline-item
                v-for="(h, i) in item.state_history"
                :key="h.id ?? i"
                :dot-color="STATE_COLORS[h.state]"
                size="small"
              >
                <template #opposite>
                  <span class="text-caption text-medium-emphasis">
                    {{ formatDateTime(h.created_at) }}
                  </span>
                </template>
                <div class="d-flex align-center gap-2 mb-1">
                  <StateChip :state="h.state" />
                  <span v-if="h.changed_by" class="text-caption text-medium-emphasis">
                    {{ $t('detail.by', { name: h.changed_by }) }}
                  </span>
                </div>
                <div v-if="h.note" class="text-body-2">{{ h.note }}</div>
              </v-timeline-item>
            </v-timeline>
            <EmptyState
              v-else
              icon="mdi-history"
              :title="$t('items.stateHistoryEmpty')"
              :text="$t('detail.historyHint')"
            />
          </v-window-item>

          <!-- Documents (cards) -->
          <v-window-item value="documents" class="pa-5">
            <div class="d-flex justify-end mb-3">
              <v-btn
                v-if="auth.canDirectEdit"
                size="small"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-plus"
                @click="openDocDialog"
              >
                {{ $t('items.actions.addDocument') }}
              </v-btn>
            </div>
            <v-list v-if="item.documents.length" class="border rounded">
              <v-list-item v-for="doc in item.documents" :key="doc.id">
                <template #prepend>
                  <v-icon icon="mdi-file-document-outline" color="primary" />
                </template>
                <v-list-item-title class="font-weight-medium">{{ doc.name }}</v-list-item-title>
                <v-list-item-subtitle>
                  <v-chip v-if="doc.doc_type" size="x-small" variant="tonal" class="me-2">
                    {{ doc.doc_type }}
                  </v-chip>
                  <a v-if="doc.url" :href="doc.url" target="_blank" rel="noopener">{{ doc.url }}</a>
                </v-list-item-subtitle>
                <template #append>
                  <v-btn
                    v-if="auth.canDirectEdit"
                    icon="mdi-delete-outline"
                    size="small"
                    variant="text"
                    color="error"
                    @click="removeDocId = doc.id"
                  />
                </template>
              </v-list-item>
            </v-list>
            <EmptyState v-else icon="mdi-file-document-outline" :title="$t('items.documentsEmpty')" />
          </v-window-item>

          <!-- Extra items (setups) -->
          <v-window-item value="extras" class="pa-5">
            <div class="d-flex justify-end mb-3">
              <v-btn
                v-if="auth.canDirectEdit"
                size="small"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-plus"
                @click="openExtraDialog"
              >
                {{ $t('items.actions.addExtra') }}
              </v-btn>
            </div>
            <v-table v-if="item.extra_items.length" class="border rounded">
              <thead>
                <tr>
                  <th>{{ $t('fields.name') }}</th>
                  <th>{{ $t('detail.partNumber') }}</th>
                  <th>{{ $t('fields.serial') }}</th>
                  <th>{{ $t('detail.signedBy') }}</th>
                  <th v-if="auth.canDirectEdit"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="ex in item.extra_items" :key="ex.id">
                  <td class="font-weight-medium">{{ ex.name }}</td>
                  <td>{{ ex.company_part_number || '—' }}</td>
                  <td>{{ ex.serial || '—' }}</td>
                  <td>{{ ex.signed_by || '—' }}</td>
                  <td v-if="auth.canDirectEdit" class="text-end">
                    <v-btn
                      icon="mdi-delete-outline"
                      size="x-small"
                      variant="text"
                      color="error"
                      @click="removeExtraId = ex.id"
                    />
                  </td>
                </tr>
              </tbody>
            </v-table>
            <EmptyState v-else icon="mdi-package-variant-closed" :title="$t('items.extras.empty')" />
          </v-window-item>

          <!-- Managers -->
          <v-window-item value="managers" class="pa-5">
            <div class="d-flex justify-end mb-3">
              <v-btn
                v-if="auth.canPropose"
                size="small"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-account-edit"
                @click="openManagersDialog"
              >
                {{ auth.canDirectEdit ? $t('detail.editManagers') : $t('detail.proposeManagers') }}
              </v-btn>
            </div>
            <v-row v-if="item.managers.length" dense>
              <v-col v-for="m in item.managers" :key="m.id" cols="12" sm="6" md="4">
                <v-card variant="outlined">
                  <v-card-text class="d-flex align-center gap-3">
                    <v-avatar color="deep-purple" variant="tonal">
                      <v-icon icon="mdi-account-tie" />
                    </v-avatar>
                    <div>
                      <div class="font-weight-medium">{{ m.full_name }}</div>
                      <div class="text-caption text-medium-emphasis">{{ m.email }}</div>
                    </div>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
            <EmptyState v-else icon="mdi-account-tie" :title="$t('detail.noManagers')" />
          </v-window-item>

          <!-- Audit -->
          <v-window-item value="audit" class="pa-5">
            <v-timeline
              v-if="audit.length"
              side="end"
              align="start"
              density="compact"
              truncate-line="both"
            >
              <v-timeline-item
                v-for="a in audit"
                :key="a.id"
                dot-color="primary"
                size="x-small"
              >
                <template #opposite>
                  <span class="text-caption text-medium-emphasis">
                    {{ formatDateTime(a.created_at) }}
                  </span>
                </template>
                <div class="font-weight-medium">{{ a.summary }}</div>
                <div v-if="a.details" class="text-caption text-medium-emphasis">{{ a.details }}</div>
                <div v-if="a.user_name" class="text-caption">— {{ a.user_name }}</div>
              </v-timeline-item>
            </v-timeline>
            <EmptyState v-else icon="mdi-clipboard-text-clock-outline" :title="$t('audit.noRecords')" />
          </v-window-item>
        </v-window>
      </v-card>

      <!-- Dialogs -->
      <ItemFormDialog
        v-model="editOpen"
        mode="edit"
        :item="item"
        :direct="auth.canDirectEdit"
        @submit="onEditSubmit"
      />
      <ItemFormDialog
        v-model="createOpen"
        mode="create"
        :type="item.type"
        :prefill="createPrefill"
        :as-template="createAsTemplate"
        :direct="auth.canDirectEdit"
        @submit="onCreateSubmit"
      />
      <v-dialog v-model="contentsOpen" max-width="640">
        <v-card rounded="lg">
          <v-card-title class="pa-4">
            {{ $t('detail.editContentsOf', { name: item.name }) }}
          </v-card-title>
          <v-divider />
          <v-card-text class="pa-4">
            <v-autocomplete
              v-model="contentsIds"
              :label="item.type === 'setup' ? $t('itemForm.includeChildrenSetup') : $t('itemForm.includeChildrenAssembly')"
              :items="contentsSelectItems"
              :loading="contentsLoading"
              item-title="title"
              item-value="value"
              multiple
              chips
              closable-chips
              :hint="$t('detail.editContentsHint')"
              persistent-hint
            >
              <template #item="{ props: itemProps, item: option }">
                <v-list-item v-bind="itemProps" :subtitle="option.raw.subtitle" />
              </template>
            </v-autocomplete>
          </v-card-text>
          <v-divider />
          <v-card-actions class="pa-3">
            <v-spacer />
            <v-btn variant="text" @click="contentsOpen = false">{{ $t('common.cancel') }}</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              :loading="contentsSaving"
              @click="saveContents"
            >
              {{ $t('common.save') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <MoveDialog
        v-model="moveOpen"
        :direct="auth.canDirectEdit"
        :current-location-id="item.location_id"
        :error="actionError"
        :loading="actionLoading"
        @confirm="onMoveConfirm"
      />
      <StateDialog
        v-model="stateOpen"
        :direct="auth.canDirectEdit"
        :current-state="item.state"
        :error="actionError"
        :loading="actionLoading"
        @confirm="onStateConfirm"
      />
      <LinkDialog
        v-model="linkOpen"
        :direct="auth.canDirectEdit"
        :item-id="item.id"
        :item-type="item.type"
        :error="actionError"
        :loading="actionLoading"
        @confirm="onLinkConfirm"
      />
      <ConfirmDialog
        v-model="unlinkOpen"
        :title="$t('detail.unlinkTitle')"
        :message="$t('detail.unlinkMsg', { name: item.name })"
        :confirm-text="$t('items.actions.unlink')"
        color="warning"
        icon="mdi-link-variant-off"
        :loading="actionLoading"
        :error="actionError"
        @confirm="onUnlinkConfirm"
      />
      <ConfirmDialog
        v-model="deleteOpen"
        :title="$t('detail.deleteTitle')"
        :message="
          auth.canDirectEdit
            ? $t('detail.deleteMsgDirect', { name: item.name })
            : $t('detail.deleteMsgPropose', { name: item.name })
        "
        :confirm-text="auth.canDirectEdit ? $t('common.delete') : $t('detail.proposeDeletion')"
        color="error"
        icon="mdi-delete-alert"
        :loading="actionLoading"
        :error="actionError"
        @confirm="onDeleteConfirm"
      />
      <ConfirmDialog
        :model-value="removeDocId !== null"
        :title="$t('detail.removeDocTitle')"
        :confirm-text="$t('common.remove')"
        @update:model-value="(v) => !v && (removeDocId = null)"
        @confirm="confirmRemoveDoc"
      />
      <ConfirmDialog
        :model-value="removeExtraId !== null"
        :title="$t('detail.removeExtraTitle')"
        :confirm-text="$t('common.remove')"
        @update:model-value="(v) => !v && (removeExtraId = null)"
        @confirm="confirmRemoveExtra"
      />
      <ProposeChangeDialog v-model="proposeOpen" :context="proposeCtx" @submitted="loadItem" />

      <!-- Add document dialog -->
      <v-dialog v-model="docOpen" max-width="520">
        <v-card rounded="lg">
          <v-card-title class="pa-4">{{ $t('items.actions.addDocument') }}</v-card-title>
          <v-divider />
          <v-card-text class="pa-4">
            <v-text-field v-model="docForm.name" :label="$t('itemForm.nameReq')" class="mb-1" />
            <v-text-field v-model="docForm.doc_type" :label="$t('detail.docType')" class="mb-1" />
            <v-text-field v-model="docForm.url" :label="$t('detail.url')" />
          </v-card-text>
          <v-divider />
          <v-card-actions class="pa-3">
            <v-spacer />
            <v-btn variant="text" @click="docOpen = false">{{ $t('common.cancel') }}</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              :loading="docSaving"
              :disabled="!docForm.name.trim()"
              @click="addDocument"
            >
              {{ $t('common.add') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Add extra dialog -->
      <v-dialog v-model="extraOpen" max-width="520">
        <v-card rounded="lg">
          <v-card-title class="pa-4">{{ $t('items.actions.addExtra') }}</v-card-title>
          <v-divider />
          <v-card-text class="pa-4">
            <v-text-field v-model="extraForm.name" :label="$t('itemForm.nameReq')" class="mb-1" />
            <v-text-field
              v-model="extraForm.company_part_number"
              :label="$t('detail.companyPartNumber')"
              class="mb-1"
            />
            <v-text-field v-model="extraForm.serial" :label="$t('fields.serial')" class="mb-1" />
            <v-text-field v-model="extraForm.signed_by" :label="$t('detail.signedBy')" />
          </v-card-text>
          <v-divider />
          <v-card-actions class="pa-3">
            <v-spacer />
            <v-btn variant="text" @click="extraOpen = false">{{ $t('common.cancel') }}</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              :loading="extraSaving"
              :disabled="!extraForm.name.trim()"
              @click="addExtra"
            >
              {{ $t('common.add') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Edit managers dialog -->
      <v-dialog v-model="managersOpen" max-width="520">
        <v-card rounded="lg">
          <v-card-title class="pa-4">
            {{ auth.canDirectEdit ? $t('detail.editManagers') : $t('detail.proposeManagerChange') }}
          </v-card-title>
          <v-divider />
          <v-card-text class="pa-4">
            <v-autocomplete
              v-model="selectedManagerIds"
              :label="$t('fields.managers')"
              multiple
              chips
              closable-chips
              :items="managerOptions.map((m) => ({ title: m.full_name, value: m.id }))"
            />
          </v-card-text>
          <v-divider />
          <v-card-actions class="pa-3">
            <v-spacer />
            <v-btn variant="text" @click="managersOpen = false">{{ $t('common.cancel') }}</v-btn>
            <v-btn color="primary" variant="flat" :loading="managersSaving" @click="saveManagers">
              {{ auth.canDirectEdit ? $t('common.save') : $t('detail.continue') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </template>

    <EmptyState
      v-else
      icon="mdi-alert-circle-outline"
      :title="$t('detail.notFound')"
      :text="$t('detail.notFoundHint')"
    />
  </v-container>
</template>
