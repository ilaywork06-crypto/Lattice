<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { auditApi, documentsApi, graphApi, itemsApi } from '@/api/services'
import { extractError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useRefsStore } from '@/stores/refs'
import { useUiStore } from '@/stores/ui'
import StateChip from '@/components/StateChip.vue'
import TypeIcon from '@/components/TypeIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import HierarchyGraph from '@/components/HierarchyGraph.vue'
import ItemFormDialog from '@/components/ItemFormDialog.vue'
import ProposeChangeDialog from '@/components/ProposeChangeDialog.vue'
import type { ProposeContext } from '@/lib/propose'
import MoveDialog from '@/components/dialogs/MoveDialog.vue'
import StateDialog from '@/components/dialogs/StateDialog.vue'
import LinkDialog from '@/components/dialogs/LinkDialog.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import { downloadBlob } from '@/utils/download'
import {
  CARD_TYPE_COLORS,
  CARD_TYPE_LABELS,
  FIELD_TYPE_ICONS,
  STATE_COLORS,
  STATE_LABELS,
  STORAGE_COLORS,
  STORAGE_LABELS,
  TYPE_LABELS,
  formatBytes,
  formatDate,
  formatDateTime,
} from '@/constants'
import type {
  AuditOut,
  DocumentOut,
  GraphNode,
  GraphOut,
  ItemCreate,
  ItemField,
  ItemListOut,
  ItemOut,
  ItemType,
  ItemUpdate,
  TemplateOut,
} from '@/api/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const refs = useRefsStore()
const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

const LIST_ROUTE: Record<ItemType, { to: string; label: string }> = {
  setup: { to: '/setups', label: 'nav.setups' },
  assembly: { to: '/assemblies', label: 'nav.assemblies' },
  card: { to: '/cards', label: 'nav.cards' },
}

// Back goes to the item's template group — correct from every entry point
// (search, graph, notification, bookmark), unlike history.back().
const backTarget = computed(() => {
  const it = item.value
  if (!it) return { to: '/', label: t('nav.dashboard') }
  const r = LIST_ROUTE[it.type]
  return { to: `${r.to}?template=${it.template.id}`, label: t(r.label) }
})

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

async function reload(updated?: ItemOut) {
  if (updated) item.value = updated
  else await loadItem()
  auditLoaded.value = false
  graph.value = null
  if (tab.value === 'hierarchy') void loadGraph()
  if (tab.value === 'audit') void loadAudit()
}

async function loadAudit() {
  if (auditLoaded.value) return
  try {
    audit.value = await auditApi.list({ item_id: itemId.value, limit: 200 })
    auditLoaded.value = true
  } catch (e) {
    ui.error(e)
  }
}

// ── hierarchy: as a graph, and as the current list ──
const graph = ref<GraphOut | null>(null)
const hierarchyView = ref<'graph' | 'list'>('graph')
async function loadGraph() {
  if (graph.value) return
  try {
    graph.value = await graphApi.item(itemId.value, true)
  } catch (e) {
    ui.error(e)
  }
}
function onGraphClick(node: GraphNode) {
  if (node.id !== itemId.value) router.push(`/items/${node.id}`)
}

watch(tab, (v) => {
  if (v === 'audit') void loadAudit()
  if (v === 'hierarchy') void loadGraph()
})

watch(itemId, () => {
  auditLoaded.value = false
  graph.value = null
  tab.value = 'overview'
  void loadItem()
})

// ── overview ──
function fieldText(f: ItemField): string {
  const d = f.display
  if (d === null || d === undefined || d === '') return '—'
  if (f.field_type === 'status') return STATE_LABELS[d as keyof typeof STATE_LABELS]
  if (Array.isArray(d)) {
    return d.map((x) => (typeof x === 'object' && x ? (x as DocumentOut).name : String(x))).join(', ')
  }
  if (typeof d === 'boolean') return d ? t('common.yes') : t('common.no')
  if (f.field_type === 'date') return formatDate(String(d))
  return String(d)
}
const fieldFiles = (f: ItemField): DocumentOut[] =>
  f.field_type === 'files' && Array.isArray(f.display) ? (f.display as DocumentOut[]) : []
const missingRequired = computed(() => item.value?.fields.filter((f) => f.missing) ?? [])

const tabs = computed(() => {
  const base = [
    { value: 'overview', label: t('items.tabs.overview'), icon: 'mdi-information-outline' },
    { value: 'hierarchy', label: t('items.tabs.hierarchy'), icon: 'mdi-file-tree-outline' },
    { value: 'history', label: t('items.tabs.stateHistory'), icon: 'mdi-history' },
    { value: 'documents', label: t('items.tabs.documents'), icon: 'mdi-file-document-outline' },
  ]
  if (item.value?.type === 'setup') {
    base.push({ value: 'extras', label: t('items.tabs.extras'), icon: 'mdi-package-variant-closed' })
  }
  base.push({ value: 'audit', label: t('items.tabs.audit'), icon: 'mdi-clipboard-text-clock-outline' })
  return base
})

// ── actions: direct (manager) vs proposal (editor; viewers: move only) ──
const editOpen = ref(false)
const moveOpen = ref(false)
const stateOpen = ref(false)
const linkOpen = ref(false)
const unlinkOpen = ref(false)
const deleteOpen = ref(false)
const createOpen = ref(false)
const proposeOpen = ref(false)
const proposeCtx = ref<ProposeContext | null>(null)
const actionError = ref('')
const actionLoading = ref(false)

function openLink() {
  actionError.value = ''
  linkOpen.value = true
}

function limitText(min: number, max: number | null): string {
  if (max == null) return min ? t('templates.limitAtLeast', { min }) : t('templates.limitNone')
  if (min === max) return t('templates.limitExactly', { n: min })
  return t('templates.limitRange', { min, max })
}

// Viewers may ask for a location change and nothing else.
const canProposeMove = computed(() => auth.isAuthenticated)

function propose(ctx: ProposeContext) {
  proposeCtx.value = ctx
  proposeOpen.value = true
}

async function direct(run: () => Promise<ItemOut>, done: string, close: () => void) {
  actionError.value = ''
  actionLoading.value = true
  try {
    await reload(await run())
    ui.success(done)
    close()
  } catch (e) {
    actionError.value = extractError(e)
  } finally {
    actionLoading.value = false
  }
}

// Edit
function onEditSaved(saved: ItemOut) {
  ui.success(t('detail.updated'))
  void reload(saved)
}
function onEditPropose(payload: ItemCreate | ItemUpdate) {
  if (!item.value) return
  propose({
    action: 'update',
    itemId: item.value.id,
    itemType: item.value.type,
    payload: payload as Record<string, unknown>,
    targetName: `${item.value.name} · ${item.value.serial}`,
    summaryLines: Object.keys((payload as ItemUpdate).values ?? {}).map((key) => ({
      label: item.value!.fields.find((f) => f.key === key)?.label ?? key,
      value: String((payload as ItemUpdate).values?.[key] ?? '—'),
    })),
  })
}

// Move — the note typed here *is* the reason; it isn't asked for again.
async function onMoveConfirm(payload: { location_id: number; note?: string }) {
  if (!item.value) return
  if (auth.canDirectEdit) {
    return direct(
      () => itemsApi.move(item.value!.id, payload.location_id, payload.note),
      t('detail.moved'),
      () => (moveOpen.value = false),
    )
  }
  moveOpen.value = false
  await refs.ensure()
  propose({
    action: 'move',
    itemId: item.value.id,
    itemType: item.value.type,
    payload,
    targetName: `${item.value.name} · ${item.value.serial}`,
    summaryLines: [
      {
        label: t('dlg.move.destination'),
        value: refs.locations.find((l) => l.id === payload.location_id)?.name ?? String(payload.location_id),
      },
    ],
    reason: payload.note,
  })
}

// State — likewise, the note is the reason.
async function onStateConfirm(payload: { state: ItemOut['state']; note?: string }) {
  if (!item.value) return
  if (auth.canDirectEdit) {
    return direct(
      () => itemsApi.changeState(item.value!.id, payload.state, payload.note),
      t('detail.stateUpdated'),
      () => (stateOpen.value = false),
    )
  }
  stateOpen.value = false
  propose({
    action: 'state_change',
    itemId: item.value.id,
    itemType: item.value.type,
    payload,
    targetName: `${item.value.name} · ${item.value.serial}`,
    summaryLines: [{ label: t('detail.newState'), value: STATE_LABELS[payload.state] }],
    reason: payload.note,
  })
}

// Link
async function onLinkConfirm(payload: { parent_id: number; parent_label?: string }) {
  if (!item.value) return
  if (auth.canDirectEdit) {
    return direct(
      () => itemsApi.link(item.value!.id, payload.parent_id),
      t('detail.linked'),
      () => (linkOpen.value = false),
    )
  }
  linkOpen.value = false
  propose({
    action: 'link',
    itemId: item.value.id,
    itemType: item.value.type,
    payload: { parent_id: payload.parent_id },
    targetName: `${item.value.name} · ${item.value.serial}`,
    summaryLines: [{ label: t('fields.parent'), value: payload.parent_label ?? String(payload.parent_id) }],
  })
}

// Unlink — say where the item now is (defaults to where its container is).
const unlinkLocation = ref<number | null>(null)
async function openUnlink() {
  actionError.value = ''
  unlinkLocation.value = null
  await refs.ensure()
  unlinkOpen.value = true
}
async function onUnlinkConfirm() {
  if (!item.value) return
  if (auth.canDirectEdit) {
    return direct(
      () => itemsApi.unlink(item.value!.id, unlinkLocation.value),
      t('detail.unlinked'),
      () => (unlinkOpen.value = false),
    )
  }
  unlinkOpen.value = false
  propose({
    action: 'unlink',
    itemId: item.value.id,
    itemType: item.value.type,
    payload: unlinkLocation.value ? { location_id: unlinkLocation.value } : {},
    targetName: `${item.value.name} · ${item.value.serial}`,
  })
}

// Delete
async function onDeleteConfirm() {
  if (!item.value) return
  if (auth.canDirectEdit) {
    actionLoading.value = true
    try {
      const target = backTarget.value.to
      await itemsApi.remove(item.value.id)
      ui.success(t('detail.deleted'))
      deleteOpen.value = false
      router.replace(target)
    } catch (e) {
      actionError.value = extractError(e)
    } finally {
      actionLoading.value = false
    }
    return
  }
  deleteOpen.value = false
  propose({
    action: 'delete',
    itemId: item.value.id,
    itemType: item.value.type,
    payload: {},
    targetName: `${item.value.name} · ${item.value.serial}`,
  })
}

// Another item from the same template
function onCreated(created: ItemOut) {
  ui.success(t('items.createdToast', { type: TYPE_LABELS[created.type] }))
  router.push(`/items/${created.id}`)
}
function onCreatePropose(payload: ItemCreate | ItemUpdate, tpl: TemplateOut) {
  propose({
    action: 'create',
    itemType: tpl.type,
    templateId: tpl.id,
    payload: payload as Record<string, unknown>,
    targetName: tpl.name,
  })
}

// ── contents (containers) ──
const contentsOpen = ref(false)
const contentsSaving = ref(false)
const contentsIds = ref<number[]>([])
const contentsOptions = ref<ItemListOut[]>([])
const contentsLoading = ref(false)

const contentsSelectItems = computed(() =>
  contentsOptions.value.map((c) => ({
    value: c.id,
    title: `${c.name} · ${c.serial}`,
    subtitle:
      c.parent_id && c.parent_id !== item.value?.id
        ? t('itemForm.willMove', { from: c.parent_label })
        : c.location_name ?? '',
  })),
)

async function openContents() {
  if (!item.value) return
  contentsIds.value = item.value.children.map((c) => c.id)
  contentsOpen.value = true
  contentsLoading.value = true
  try {
    contentsOptions.value = (await itemsApi.list({
      child_of_template: item.value.template.id,
      include_destroyed: false,
    }))
      .filter((c) => c.id !== item.value?.id)
      .sort((a, b) => Number(!!a.parent_id) - Number(!!b.parent_id) || a.serial.localeCompare(b.serial))
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
    await reload(await itemsApi.setChildren(item.value.id, contentsIds.value))
    ui.success(t('detail.contentsUpdated'))
    contentsOpen.value = false
  } catch (e) {
    ui.error(e)
  } finally {
    contentsSaving.value = false
  }
}

// ── documents: real uploads (or a link) ──
const docOpen = ref(false)
const docForm = reactive<{ files: File[]; name: string; url: string; doc_type: string; mode: 'file' | 'link' }>({
  files: [],
  name: '',
  url: '',
  doc_type: '',
  mode: 'file',
})
const docSaving = ref(false)
const removeDocId = ref<number | null>(null)

function openDocDialog() {
  Object.assign(docForm, { files: [], name: '', url: '', doc_type: '', mode: 'file' })
  docOpen.value = true
}

const docReady = computed(() =>
  docForm.mode === 'file' ? docForm.files.length > 0 : !!docForm.url.trim() && !!docForm.name.trim(),
)

async function addDocument() {
  if (!item.value || !docReady.value) return
  docSaving.value = true
  try {
    if (docForm.mode === 'file') {
      for (const f of docForm.files) {
        await itemsApi.addDocument(item.value.id, {
          file: f,
          name: docForm.files.length === 1 ? docForm.name.trim() || undefined : undefined,
          doc_type: docForm.doc_type.trim() || undefined,
        })
      }
    } else {
      await itemsApi.addDocument(item.value.id, {
        name: docForm.name.trim(),
        url: docForm.url.trim(),
        doc_type: docForm.doc_type.trim() || undefined,
      })
    }
    await reload()
    ui.success(t('detail.docAdded'))
    docOpen.value = false
  } catch (e) {
    ui.error(e)
  } finally {
    docSaving.value = false
  }
}

async function downloadDoc(doc: DocumentOut) {
  if (!doc.is_file) {
    if (doc.url) window.open(doc.url, '_blank', 'noopener')
    return
  }
  try {
    downloadBlob(await documentsApi.download(doc.id), doc.original_filename || doc.name)
  } catch (e) {
    ui.error(e)
  }
}

async function confirmRemoveDoc() {
  if (!item.value || removeDocId.value == null) return
  try {
    await itemsApi.removeDocument(item.value.id, removeDocId.value)
    await reload()
    ui.success(t('detail.docRemoved'))
  } catch (e) {
    ui.error(e)
  } finally {
    removeDocId.value = null
  }
}

// ── extras (setups) ──
const extraOpen = ref(false)
const extraForm = reactive({ name: '', company_part_number: '', serial: '', signed_by: '' })
const extraSaving = ref(false)
const removeExtraId = ref<number | null>(null)

function openExtraDialog() {
  Object.assign(extraForm, { name: '', company_part_number: '', serial: '', signed_by: '' })
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
    await reload()
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
    await reload()
    ui.success(t('detail.extraRemoved'))
  } catch (e) {
    ui.error(e)
  } finally {
    removeExtraId.value = null
  }
}

onMounted(loadItem)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <v-btn variant="text" prepend-icon="mdi-arrow-left" class="mb-3 flip-rtl-icon" :to="backTarget.to">
      {{ $t('detail.backTo', { target: backTarget.label }) }}
    </v-btn>

    <v-skeleton-loader v-if="loading && !item" type="article, list-item-three-line@3" />

    <template v-else-if="item">
      <!-- Header -->
      <v-card variant="flat" border class="mb-4">
        <v-card-text class="pa-5">
          <div class="d-flex flex-wrap align-center justify-space-between gap-4">
            <div class="d-flex align-center gap-4">
              <v-avatar :color="STATE_COLORS[item.state]" variant="tonal" rounded="lg" size="60">
                <TypeIcon :type="item.type" :size="30" />
              </v-avatar>
              <div>
                <div class="d-flex align-center gap-2 flex-wrap">
                  <h1 class="text-h5 font-weight-bold"><bdi>{{ item.name }}</bdi></h1>
                  <v-chip size="small" variant="outlined" label prepend-icon="mdi-barcode" class="font-mono">
                    {{ item.serial }}
                  </v-chip>
                  <StateChip :state="item.state" />
                </div>
                <div class="text-body-2 text-medium-emphasis mt-1 d-flex align-center flex-wrap gap-3">
                  <RouterLink :to="`/templates/${item.template.id}`" class="text-medium-emphasis">
                    <v-icon icon="mdi-shape-outline" size="14" /> {{ $t('detail.templateLink', { name: item.template.name }) }}
                  </RouterLink>
                  <v-chip v-if="item.card_type" :color="CARD_TYPE_COLORS[item.card_type]" size="x-small" variant="flat" label>
                    {{ CARD_TYPE_LABELS[item.card_type] }}
                  </v-chip>
                  <span v-if="item.parent">
                    <v-icon icon="mdi-link-variant" size="14" />
                    <RouterLink :to="`/items/${item.parent.id}`" class="text-medium-emphasis">
                      {{ $t('detail.insideOf') }} <bdi>{{ item.parent.name }} · {{ item.parent.serial }}</bdi>
                    </RouterLink>
                  </span>
                  <v-chip v-if="!item.is_complete" color="warning" size="x-small" variant="tonal" prepend-icon="mdi-alert-outline">
                    {{ $t('detail.incomplete') }}
                  </v-chip>
                  <span v-if="item.location">
                    <v-icon icon="mdi-map-marker" size="14" /> <bdi>{{ item.location.name }}</bdi>
                    <v-icon v-if="item.location.is_desiccator" icon="mdi-water-off" size="14" color="cyan-darken-2" />
                  </span>
                  <v-chip
                    v-if="item.storage_status"
                    :color="STORAGE_COLORS[item.storage_status]"
                    size="x-small"
                    variant="tonal"
                  >
                    {{ STORAGE_LABELS[item.storage_status] }}
                  </v-chip>
                  <span v-if="item.tracking === 'quantity'">
                    <v-icon icon="mdi-counter" size="14" /> {{ $t('detail.units', { n: item.quantity }) }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="d-flex align-center gap-2">
              <v-btn
                v-if="auth.canPropose"
                color="primary"
                variant="flat"
                prepend-icon="mdi-pencil"
                @click="editOpen = true"
              >
                {{ auth.canDirectEdit ? $t('detail.edit') : $t('detail.proposeEdit') }}
              </v-btn>
              <!-- A viewer's one action: ask for the item to be moved -->
              <v-btn
                v-else-if="canProposeMove"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-map-marker-radius"
                :disabled="!!item.parent"
                @click="(actionError = ''), (moveOpen = true)"
              >
                {{ $t('detail.proposeMove') }}
              </v-btn>
              <v-menu v-if="auth.canPropose" location="bottom end">
                <template #activator="{ props }">
                  <v-btn v-bind="props" variant="tonal" icon="mdi-dots-vertical" />
                </template>
                <v-list density="compact" nav>
                  <!-- A linked item is physically inside its parent, so it has
                       no location of its own to change. -->
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
                    :title="item.parent ? $t('detail.changeParent') : $t('items.actions.link')"
                    @click="openLink"
                  />
                  <v-list-item
                    v-if="item.parent"
                    prepend-icon="mdi-link-variant-off"
                    :title="$t('detail.unlinkFromParent')"
                    @click="openUnlink"
                  />
                  <v-divider class="my-1" />
                  <v-list-item
                    prepend-icon="mdi-plus-box-multiple-outline"
                    :title="$t('detail.anotherFromTemplate')"
                    @click="createOpen = true"
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

          <v-alert
            v-if="missingRequired.length"
            type="warning"
            variant="tonal"
            density="compact"
            class="mt-4"
            icon="mdi-alert-outline"
          >
            {{ $t('detail.missingRequired', { fields: missingRequired.map((f) => f.label).join(', ') }) }}
          </v-alert>
        </v-card-text>
      </v-card>

      <!-- Tabs -->
      <v-card variant="flat" border>
        <v-tabs v-model="tab" color="primary" show-arrows>
          <v-tab v-for="tb in tabs" :key="tb.value" :value="tb.value" :prepend-icon="tb.icon">
            <bdi>{{ tb.label }}</bdi>
          </v-tab>
        </v-tabs>
        <v-divider />

        <v-window v-model="tab">
          <!-- Overview: the template's fields, white (template) and grey (item) -->
          <v-window-item value="overview" class="pa-5">
            <v-row dense>
              <v-col v-for="f in item.fields" :key="f.field_id" cols="12" sm="6" md="4">
                <div class="field-cell" :class="f.mode === 'item' ? 'is-grey' : 'is-white'">
                  <v-icon :icon="FIELD_TYPE_ICONS[f.field_type]" size="20" class="text-medium-emphasis" />
                  <div class="overflow-hidden">
                    <div class="text-caption text-medium-emphasis">
                      <bdi>{{ f.label }}</bdi><span v-if="f.required" class="text-error">*</span>
                      <v-icon v-if="f.mode === 'fixed'" icon="mdi-lock-outline" size="12" class="ms-1" :title="$t('detail.fromTemplate')" />
                    </div>
                    <div v-if="fieldFiles(f).length" class="d-flex flex-wrap gap-1 mt-1">
                      <v-chip
                        v-for="d in fieldFiles(f)"
                        :key="d.id"
                        size="x-small"
                        prepend-icon="mdi-paperclip"
                        @click="downloadDoc(d)"
                      >
                        <bdi>{{ d.name }}</bdi>
                      </v-chip>
                    </div>
                    <div v-else class="text-body-2 font-weight-medium text-break" :class="{ 'text-warning': f.missing }">
                      <bdi>{{ f.missing ? $t('detail.missing') : fieldText(f) }}</bdi>
                    </div>
                  </div>
                  <v-spacer />
                  <v-btn
                    v-if="auth.canPropose && f.field_type === 'parent'"
                    icon="mdi-link-variant"
                    size="x-small"
                    variant="text"
                    color="primary"
                    :title="item.parent ? $t('detail.changeParent') : $t('detail.linkToParent')"
                    :aria-label="item.parent ? $t('detail.changeParent') : $t('detail.linkToParent')"
                    @click="openLink"
                  />
                  <v-btn
                    v-else-if="canProposeMove && f.field_type === 'location' && !item.parent"
                    icon="mdi-map-marker-radius"
                    size="x-small"
                    variant="text"
                    color="primary"
                    :title="$t('items.actions.move')"
                    :aria-label="$t('items.actions.move')"
                    @click="(actionError = ''), (moveOpen = true)"
                  />
                  <v-btn
                    v-else-if="auth.canPropose && f.field_type === 'status'"
                    icon="mdi-swap-horizontal"
                    size="x-small"
                    variant="text"
                    color="primary"
                    :title="$t('items.actions.changeState')"
                    :aria-label="$t('items.actions.changeState')"
                    @click="(actionError = ''), (stateOpen = true)"
                  />
                </div>
              </v-col>
              <v-col cols="12" sm="6" md="4">
                <div class="field-cell">
                  <v-icon icon="mdi-clock-plus-outline" size="20" class="text-medium-emphasis" />
                  <div>
                    <div class="text-caption text-medium-emphasis">{{ $t('fields.createdAt') }}</div>
                    <div class="text-body-2 font-weight-medium">{{ formatDateTime(item.created_at) }}</div>
                  </div>
                </div>
              </v-col>
              <v-col cols="12" sm="6" md="4">
                <div class="field-cell">
                  <v-icon icon="mdi-clock-edit-outline" size="20" class="text-medium-emphasis" />
                  <div>
                    <div class="text-caption text-medium-emphasis">{{ $t('fields.updatedAt') }}</div>
                    <div class="text-body-2 font-weight-medium">{{ formatDateTime(item.updated_at) }}</div>
                  </div>
                </div>
              </v-col>
            </v-row>
            <EmptyState v-if="!item.fields.length" icon="mdi-form-select" :title="$t('detail.noFields')" />
          </v-window-item>

          <!-- Hierarchy -->
          <v-window-item value="hierarchy" class="pa-5">
            <!-- Where this item sits, and the way to put it somewhere -->
            <div v-if="item.type !== 'setup'" class="parent-bar d-flex align-center flex-wrap gap-3 mb-4">
              <v-icon icon="mdi-link-variant" color="primary" />
              <template v-if="item.parent">
                <span class="text-medium-emphasis">{{ $t('detail.parent') }}:</span>
                <RouterLink :to="`/items/${item.parent.id}`" class="text-primary font-weight-medium">
                  <bdi>{{ item.parent.name }} · {{ item.parent.serial }}</bdi>
                </RouterLink>
                <StateChip :state="item.parent.state" />
              </template>
              <span v-else class="text-medium-emphasis">{{ $t('detail.noParent') }}</span>
              <v-spacer />
              <template v-if="auth.canPropose">
                <v-btn
                  size="small"
                  color="primary"
                  variant="tonal"
                  prepend-icon="mdi-link-variant"
                  :disabled="!item.parent_templates.length"
                  @click="openLink"
                >
                  {{ item.parent ? $t('detail.changeParent') : $t('detail.linkToParent') }}
                </v-btn>
                <v-btn
                  v-if="item.parent"
                  size="small"
                  color="warning"
                  variant="text"
                  prepend-icon="mdi-link-variant-off"
                  @click="openUnlink"
                >
                  {{ $t('items.actions.unlink') }}
                </v-btn>
              </template>
            </div>
            <v-alert
              v-if="item.type !== 'setup' && !item.parent_templates.length"
              type="info"
              variant="tonal"
              density="compact"
              class="mb-4"
            >
              {{ $t('detail.noParentTemplates', { name: item.template.name }) }}
              <RouterLink :to="`/templates/${item.template.id}`" class="text-primary">{{ $t('detail.openTemplates') }}</RouterLink>
            </v-alert>

            <!-- What a container holds against its template's limits -->
            <div v-if="item.composition.length" class="mb-5">
              <div class="text-overline text-medium-emphasis mb-2">{{ $t('detail.composition') }}</div>
              <v-table density="compact" class="border rounded">
                <thead>
                  <tr>
                    <th>{{ $t('fields.template') }}</th>
                    <th class="text-center">{{ $t('detail.inside') }}</th>
                    <th class="text-center">{{ $t('detail.allowed') }}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in item.composition" :key="row.template.id">
                    <td>
                      <RouterLink :to="`/templates/${row.template.id}`" class="text-primary">
                        <bdi>{{ row.template.name }}</bdi>
                      </RouterLink>
                    </td>
                    <td class="text-center font-weight-medium">{{ row.count }}</td>
                    <td class="text-center text-medium-emphasis">{{ limitText(row.min_count, row.max_count) }}</td>
                    <td class="text-end">
                      <v-chip v-if="row.missing" color="warning" size="x-small" variant="tonal">
                        {{ $t('detail.missingN', { n: row.missing }) }}
                      </v-chip>
                      <v-chip v-else-if="row.is_full" color="info" size="x-small" variant="tonal">{{ $t('detail.full') }}</v-chip>
                      <v-chip v-else color="success" size="x-small" variant="tonal">{{ $t('detail.ok') }}</v-chip>
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </div>

            <div class="d-flex align-center gap-2 mb-4">
              <v-btn-toggle v-model="hierarchyView" density="comfortable" variant="outlined" mandatory rounded="lg" color="primary">
                <v-btn value="graph" prepend-icon="mdi-graph-outline">{{ $t('detail.asGraph') }}</v-btn>
                <v-btn value="list" prepend-icon="mdi-format-list-bulleted">{{ $t('detail.asList') }}</v-btn>
              </v-btn-toggle>
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

            <HierarchyGraph
              v-if="hierarchyView === 'graph'"
              :data="graph"
              kind="items"
              height="480px"
              :focus-id="item.id"
              @node-click="onGraphClick"
            />

            <template v-else>
              <v-alert
                v-if="item.parent"
                type="info"
                variant="tonal"
                density="compact"
                class="mb-4"
                icon="mdi-map-marker-off-outline"
              >
                <i18n-t keypath="detail.moveLocked" scope="global">
                  <template #name><strong><bdi>{{ item.name }}</bdi></strong></template>
                  <template #parent>
                    <RouterLink :to="`/items/${item.parent.id}`" class="text-primary">
                      <bdi>{{ item.parent.name }} · {{ item.parent.serial }}</bdi>
                    </RouterLink>
                  </template>
                </i18n-t>
              </v-alert>

              <div class="text-overline text-medium-emphasis mb-2">
                {{ $t('detail.children', { n: item.children.length }) }}
              </div>
              <v-row v-if="item.children.length" dense>
                <v-col v-for="child in item.children" :key="child.id" cols="12" sm="6" md="4">
                  <v-card variant="outlined" class="clickable-row" @click="router.push(`/items/${child.id}`)">
                    <v-card-text class="d-flex align-center gap-3">
                      <TypeIcon :type="child.type" :size="22" />
                      <div class="flex-grow-1 overflow-hidden">
                        <div class="font-weight-medium text-truncate"><bdi>{{ child.name }}</bdi></div>
                        <div class="text-caption text-medium-emphasis">{{ child.serial }}</div>
                      </div>
                      <StateChip :state="child.state" />
                    </v-card-text>
                  </v-card>
                </v-col>
              </v-row>
              <EmptyState v-else icon="mdi-file-tree-outline" :title="$t('detail.noChildren')" :text="$t('detail.noChildrenHint')" />
              <div v-if="item.child_templates.length" class="text-caption text-medium-emphasis mt-3">
                {{ $t('detail.mayContain', { names: item.child_templates.map((c) => c.name).join(', ') }) }}
              </div>
            </template>
          </v-window-item>

          <!-- State history -->
          <v-window-item value="history" class="pa-5">
            <v-timeline v-if="item.state_history.length" side="end" align="start" density="comfortable" truncate-line="both">
              <v-timeline-item
                v-for="h in [...item.state_history].reverse()"
                :key="h.id"
                :dot-color="STATE_COLORS[h.state]"
                size="small"
              >
                <template #opposite>
                  <span class="text-caption text-medium-emphasis">{{ formatDateTime(h.changed_at) }}</span>
                </template>
                <div class="d-flex align-center gap-2 mb-1">
                  <StateChip :state="h.state" />
                  <span v-if="h.changed_by_name" class="text-caption text-medium-emphasis">
                    {{ $t('detail.by', { name: h.changed_by_name }) }}
                  </span>
                </div>
                <div v-if="h.note" class="text-body-2"><bdi>{{ h.note }}</bdi></div>
              </v-timeline-item>
            </v-timeline>
            <EmptyState v-else icon="mdi-history" :title="$t('items.stateHistoryEmpty')" :text="$t('detail.historyHint')" />
          </v-window-item>

          <!-- Documents: uploaded files and links -->
          <v-window-item value="documents" class="pa-5">
            <div class="d-flex justify-end mb-3">
              <v-btn
                v-if="auth.canDirectEdit"
                size="small"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-upload"
                @click="openDocDialog"
              >
                {{ $t('items.actions.addDocument') }}
              </v-btn>
            </div>
            <v-list v-if="item.documents.length" class="border rounded">
              <v-list-item v-for="doc in item.documents" :key="doc.id" @click="downloadDoc(doc)">
                <template #prepend>
                  <v-icon :icon="doc.is_file ? 'mdi-file-download-outline' : 'mdi-link-variant'" color="primary" />
                </template>
                <v-list-item-title class="font-weight-medium"><bdi>{{ doc.name }}</bdi></v-list-item-title>
                <v-list-item-subtitle>
                  <v-chip v-if="doc.doc_type" size="x-small" variant="tonal" class="me-2">{{ doc.doc_type }}</v-chip>
                  <span v-if="doc.is_file">{{ formatBytes(doc.size_bytes) }} · {{ formatDateTime(doc.created_at) }}</span>
                  <span v-else>{{ doc.url }}</span>
                </v-list-item-subtitle>
                <template #append>
                  <v-btn
                    v-if="auth.canDirectEdit"
                    icon="mdi-delete-outline"
                    size="small"
                    variant="text"
                    color="error"
                    @click.stop="removeDocId = doc.id"
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
                  <td class="font-weight-medium"><bdi>{{ ex.name }}</bdi></td>
                  <td>{{ ex.company_part_number || '—' }}</td>
                  <td>{{ ex.serial || '—' }}</td>
                  <td>{{ ex.signed_by || '—' }}</td>
                  <td v-if="auth.canDirectEdit" class="text-end">
                    <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error" @click="removeExtraId = ex.id" />
                  </td>
                </tr>
              </tbody>
            </v-table>
            <EmptyState v-else icon="mdi-package-variant-closed" :title="$t('items.extras.empty')" />
          </v-window-item>

          <!-- Audit -->
          <v-window-item value="audit" class="pa-5">
            <v-timeline v-if="audit.length" side="end" align="start" density="compact" truncate-line="both">
              <v-timeline-item v-for="a in audit" :key="a.id" dot-color="primary" size="x-small">
                <template #opposite>
                  <span class="text-caption text-medium-emphasis">{{ formatDateTime(a.created_at) }}</span>
                </template>
                <div class="font-weight-medium"><bdi>{{ a.summary }}</bdi></div>
                <div v-if="a.user_name" class="text-caption">— <bdi>{{ a.user_name }}</bdi></div>
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
        @saved="onEditSaved"
        @propose="onEditPropose"
      />
      <ItemFormDialog
        v-model="createOpen"
        mode="create"
        :type="item.type"
        :template-id="item.template.id"
        :direct="auth.canDirectEdit"
        @saved="onCreated"
        @propose="onCreatePropose"
      />

      <v-dialog v-model="contentsOpen" max-width="640">
        <v-card rounded="lg">
          <v-card-title class="pa-4">{{ $t('detail.editContentsOf', { name: item.name }) }}</v-card-title>
          <v-divider />
          <v-card-text class="pa-4">
            <v-autocomplete
              v-model="contentsIds"
              :label="$t('itemForm.contents')"
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
            <v-btn color="primary" variant="flat" :loading="contentsSaving" @click="saveContents">
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
        :template-id="item.template.id"
        :current-parent-id="item.parent_id"
        :parent-templates="item.parent_templates"
        :error="actionError"
        :loading="actionLoading"
        @confirm="onLinkConfirm"
      />

      <v-dialog v-model="unlinkOpen" max-width="520">
        <v-card rounded="lg">
          <v-card-title class="d-flex align-center gap-2 pa-4">
            <v-icon icon="mdi-link-variant-off" color="warning" />
            <span class="text-h6">{{ $t('detail.unlinkTitle') }}</span>
          </v-card-title>
          <v-divider />
          <v-card-text class="pa-4">
            <p class="text-body-2 mb-4">{{ $t('detail.unlinkMsg', { name: `${item.name} · ${item.serial}` }) }}</p>
            <v-autocomplete
              v-model="unlinkLocation"
              :label="$t('detail.unlinkWhere')"
              :items="refs.locations.map((l) => ({ title: l.name, value: l.id, subtitle: l.is_desiccator ? $t('fieldInput.desiccator') : '' }))"
              clearable
              :hint="$t('detail.unlinkWhereHint', { where: item.location?.name ?? '—' })"
              persistent-hint
            />
            <v-alert v-if="actionError" type="error" variant="tonal" density="compact" class="mt-3" :text="actionError" />
          </v-card-text>
          <v-divider />
          <v-card-actions class="pa-3">
            <v-spacer />
            <v-btn variant="text" @click="unlinkOpen = false">{{ $t('common.cancel') }}</v-btn>
            <v-btn color="warning" variant="flat" :loading="actionLoading" @click="onUnlinkConfirm">
              {{ auth.canDirectEdit ? $t('items.actions.unlink') : $t('dlg.continueToProposal') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <ConfirmDialog
        v-model="deleteOpen"
        :title="$t('detail.deleteTitle')"
        :message="
          auth.canDirectEdit
            ? $t('detail.deleteMsgDirect', { name: `${item.name} · ${item.serial}` })
            : $t('detail.deleteMsgPropose', { name: `${item.name} · ${item.serial}` })
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
      <ProposeChangeDialog v-model="proposeOpen" :context="proposeCtx" @submitted="reload()" />

      <!-- Add document: upload a file (or record a link) -->
      <v-dialog v-model="docOpen" max-width="560">
        <v-card rounded="lg">
          <v-card-title class="pa-4">{{ $t('items.actions.addDocument') }}</v-card-title>
          <v-divider />
          <v-card-text class="pa-4">
            <v-btn-toggle v-model="docForm.mode" mandatory density="comfortable" variant="outlined" rounded="lg" color="primary" class="mb-4">
              <v-btn value="file" prepend-icon="mdi-upload">{{ $t('detail.uploadFile') }}</v-btn>
              <v-btn value="link" prepend-icon="mdi-link-variant">{{ $t('detail.addLink') }}</v-btn>
            </v-btn-toggle>
            <template v-if="docForm.mode === 'file'">
              <v-file-input
                v-model="docForm.files"
                :label="$t('detail.chooseFiles')"
                multiple
                chips
                show-size
                prepend-icon=""
                prepend-inner-icon="mdi-paperclip"
              />
              <v-text-field
                v-if="docForm.files.length === 1"
                v-model="docForm.name"
                :label="$t('detail.docNameOptional')"
              />
            </template>
            <template v-else>
              <v-text-field v-model="docForm.name" :label="$t('itemForm.nameReq')" />
              <v-text-field v-model="docForm.url" :label="$t('detail.url')" placeholder="https://" />
            </template>
            <v-text-field v-model="docForm.doc_type" :label="$t('detail.docType')" />
          </v-card-text>
          <v-divider />
          <v-card-actions class="pa-3">
            <v-spacer />
            <v-btn variant="text" @click="docOpen = false">{{ $t('common.cancel') }}</v-btn>
            <v-btn color="primary" variant="flat" :loading="docSaving" :disabled="!docReady" @click="addDocument">
              {{ $t('common.add') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Add extra -->
      <v-dialog v-model="extraOpen" max-width="520">
        <v-card rounded="lg">
          <v-card-title class="pa-4">{{ $t('items.actions.addExtra') }}</v-card-title>
          <v-divider />
          <v-card-text class="pa-4">
            <v-text-field v-model="extraForm.name" :label="$t('itemForm.nameReq')" class="mb-1" />
            <v-text-field v-model="extraForm.company_part_number" :label="$t('detail.companyPartNumber')" class="mb-1" />
            <v-text-field v-model="extraForm.serial" :label="$t('fields.serial')" class="mb-1" />
            <v-text-field v-model="extraForm.signed_by" :label="$t('detail.signedBy')" />
          </v-card-text>
          <v-divider />
          <v-card-actions class="pa-3">
            <v-spacer />
            <v-btn variant="text" @click="extraOpen = false">{{ $t('common.cancel') }}</v-btn>
            <v-btn color="primary" variant="flat" :loading="extraSaving" :disabled="!extraForm.name.trim()" @click="addExtra">
              {{ $t('common.add') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </template>

    <EmptyState v-else icon="mdi-alert-circle-outline" :title="$t('detail.notFound')" :text="$t('detail.notFoundHint')" />
  </v-container>
</template>

<style scoped>
.field-cell {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 8px;
}
.field-cell.is-grey {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.font-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.parent-bar {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  padding: 10px 14px;
}
</style>
