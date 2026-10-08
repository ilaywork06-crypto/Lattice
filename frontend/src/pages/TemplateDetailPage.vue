<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { auditApi, dataApi, documentsApi, graphApi, templatesApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import EmptyState from '@/components/EmptyState.vue'
import HierarchyGraph from '@/components/HierarchyGraph.vue'
import ItemFormDialog from '@/components/ItemFormDialog.vue'
import ProposeChangeDialog from '@/components/ProposeChangeDialog.vue'
import TemplateEditorDialog from '@/components/TemplateEditorDialog.vue'
import TypeIcon from '@/components/TypeIcon.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import type { ProposeContext } from '@/lib/propose'
import { downloadBlob } from '@/utils/download'
import {
  ACTIVE_STATES,
  CARD_TYPE_COLORS,
  CARD_TYPE_LABELS,
  FIELD_MODE_LABELS,
  FIELD_TYPE_ICONS,
  FIELD_TYPE_LABELS,
  STATE_COLORS,
  STATE_LABELS,
  TRACKING_LABELS,
  TYPE_LABELS,
  fieldLabel,
  formatBytes,
  formatDateTime,
} from '@/constants'
import type {
  AuditOut,
  DocumentOut,
  GraphNode,
  GraphOut,
  ItemCreate,
  ItemOut,
  ItemUpdate,
  TemplateCreate,
  TemplateFieldOut,
  TemplateOut,
} from '@/api/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

const LIST_ROUTE = { setup: '/setups', assembly: '/assemblies', card: '/cards' } as const

const id = computed(() => Number(route.params.id))
const tpl = ref<TemplateOut | null>(null)
const loading = ref(true)
const tab = ref('fields')
const graph = ref<GraphOut | null>(null)
const audit = ref<AuditOut[]>([])

async function load() {
  loading.value = true
  try {
    tpl.value = await templatesApi.get(id.value)
  } catch (e) {
    ui.error(e)
    tpl.value = null
  } finally {
    loading.value = false
  }
}

async function loadTab() {
  try {
    if (tab.value === 'graph' && !graph.value) graph.value = await graphApi.templates(id.value)
    if (tab.value === 'history' && !audit.value.length) {
      audit.value = await auditApi.list({ template_id: id.value, limit: 200 })
    }
  } catch (e) {
    ui.error(e)
  }
}
watch(tab, loadTab)
watch(id, () => {
  graph.value = null
  audit.value = []
  tab.value = 'fields'
  void load()
})

function shown(f: TemplateFieldOut): string {
  if (f.mode === 'choice' || f.field_type === 'enum') {
    const opts = f.options_display.length ? f.options_display : ((f.config.options ?? []) as string[])
    return opts.join(' · ')
  }
  if (f.mode !== 'fixed') return '—'
  const d = f.fixed_display
  if (d === null || d === undefined || d === '') return '—'
  if (Array.isArray(d)) return d.join(', ')
  if (typeof d === 'boolean') return d ? t('common.yes') : t('common.no')
  return String(d)
}

function formatOf(f: TemplateFieldOut): string {
  if (f.config.pattern) return f.config.pattern
  if (f.field_type === 'description') return t('fieldInput.minChars', { n: f.config.min_length ?? 8 })
  return ''
}

// ── edit / delete ──
const editorOpen = ref(false)
const proposeOpen = ref(false)
const proposeCtx = ref<ProposeContext | null>(null)
const deleteOpen = ref(false)
const deleting = ref(false)

async function onEditSubmit(payload: TemplateCreate | Partial<TemplateCreate>) {
  if (!tpl.value) return
  if (auth.canDirectEdit) {
    try {
      tpl.value = await templatesApi.update(tpl.value.id, payload)
      ui.success(t('templates.updated'))
      editorOpen.value = false
      graph.value = null
      audit.value = []
    } catch (e) {
      ui.error(e)
    }
    return
  }
  editorOpen.value = false
  proposeCtx.value = {
    action: 'template_update',
    templateId: tpl.value.id,
    itemType: tpl.value.type,
    payload: payload as Record<string, unknown>,
    targetName: tpl.value.name,
  }
  proposeOpen.value = true
}

// ── duplicate (a new template prefilled from this one) ──
const duplicateOpen = ref(false)
async function onDuplicateSubmit(payload: TemplateCreate | Partial<TemplateCreate>) {
  const body = payload as TemplateCreate
  if (auth.canDirectEdit) {
    try {
      const created = await templatesApi.create(body)
      ui.success(t('templates.duplicated', { name: created.name }))
      duplicateOpen.value = false
      router.push(`/templates/${created.id}`)
    } catch (e) {
      ui.error(e)
    }
    return
  }
  duplicateOpen.value = false
  proposeCtx.value = {
    action: 'template_create',
    itemType: body.type,
    payload: body as unknown as Record<string, unknown>,
    targetName: body.name,
    reason: t('templates.duplicateReason', { name: tpl.value?.name ?? '' }),
  }
  proposeOpen.value = true
}

function limitLabel(min: number, max: number | null): string {
  if (!min && max == null) return ''
  if (max == null) return t('templates.limitAtLeast', { min })
  if (min === max) return t('templates.limitExactly', { n: min })
  return t('templates.limitRange', { min, max })
}

async function remove() {
  if (!tpl.value) return
  deleting.value = true
  try {
    await templatesApi.remove(tpl.value.id)
    ui.success(t('templates.deleted'))
    router.replace('/templates')
  } catch (e) {
    ui.error(e)
  } finally {
    deleting.value = false
    deleteOpen.value = false
  }
}

// ── create an item from this template ──
const itemOpen = ref(false)
function onItemSaved(item: ItemOut) {
  ui.success(t('items.createdToast', { type: TYPE_LABELS[item.type] }))
  router.push(`/items/${item.id}`)
}
function onItemPropose(payload: ItemCreate | ItemUpdate, template: TemplateOut) {
  proposeCtx.value = {
    action: 'create',
    itemType: template.type,
    templateId: template.id,
    payload: payload as Record<string, unknown>,
    targetName: template.name,
  }
  proposeOpen.value = true
}

// ── template-level files ──
const uploadingField = ref<number | null>(null)
async function uploadTemplateFiles(field: TemplateFieldOut, files: File | File[] | null) {
  const list = Array.isArray(files) ? files : files ? [files] : []
  if (!tpl.value || !list.length) return
  uploadingField.value = field.id
  try {
    for (const f of list) await templatesApi.uploadFieldFile(tpl.value.id, field.id, f)
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    uploadingField.value = null
  }
}
async function removeTemplateFile(doc: DocumentOut) {
  if (!tpl.value) return
  try {
    await templatesApi.removeFile(tpl.value.id, doc.id)
    await load()
  } catch (e) {
    ui.error(e)
  }
}
async function downloadDoc(doc: DocumentOut) {
  try {
    downloadBlob(await documentsApi.download(doc.id), doc.original_filename || doc.name)
  } catch (e) {
    ui.error(e)
  }
}

async function downloadImportFile() {
  if (!tpl.value) return
  try {
    downloadBlob(
      await dataApi.template({ template_id: tpl.value.id }),
      `lattice_import_${tpl.value.serial_prefix}.xlsx`,
    )
  } catch (e) {
    ui.error(e)
  }
}

function onGraphClick(node: GraphNode) {
  if (node.id !== id.value) router.push(`/templates/${node.id}`)
}

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <v-btn variant="text" prepend-icon="mdi-arrow-left" class="mb-3 flip-rtl-icon" to="/templates">
      {{ $t('detail.backTo', { target: $t('nav.templates') }) }}
    </v-btn>

    <v-skeleton-loader v-if="loading && !tpl" type="article, list-item-three-line@3" />

    <template v-else-if="tpl">
      <v-card variant="flat" border class="mb-4">
        <v-card-text class="pa-5">
          <div class="d-flex flex-wrap align-center justify-space-between gap-4">
            <div class="d-flex align-center gap-4">
              <v-avatar color="primary" variant="tonal" rounded="lg" size="60">
                <TypeIcon :type="tpl.type" :size="30" />
              </v-avatar>
              <div>
                <div class="d-flex align-center gap-2 flex-wrap">
                  <h1 class="text-h5 font-weight-bold"><bdi>{{ tpl.name }}</bdi></h1>
                  <v-chip size="small" variant="outlined" label prepend-icon="mdi-barcode">{{ tpl.serial_prefix }}</v-chip>
                  <v-chip v-if="tpl.card_type" :color="CARD_TYPE_COLORS[tpl.card_type]" size="small" variant="flat" label>
                    {{ CARD_TYPE_LABELS[tpl.card_type] }}
                  </v-chip>
                </div>
                <div class="text-body-2 text-medium-emphasis mt-1 d-flex flex-wrap gap-3">
                  <span>{{ $t('templates.typeOf', { type: TYPE_LABELS[tpl.type] }) }}</span>
                  <span v-if="tpl.tracking">{{ TRACKING_LABELS[tpl.tracking] }}</span>
                  <span>{{ $t('templates.nextSerial', { serial: tpl.next_serial }) }}</span>
                </div>
              </div>
            </div>
            <div class="d-flex flex-wrap align-center gap-2">
              <v-btn variant="tonal" prepend-icon="mdi-format-list-bulleted" :to="`${LIST_ROUTE[tpl.type]}?template=${tpl.id}`">
                {{ $t('templates.viewUnits', { n: tpl.counts.total }) }}
              </v-btn>
              <v-btn variant="tonal" prepend-icon="mdi-microsoft-excel" @click="downloadImportFile">
                {{ $t('templates.importFile') }}
              </v-btn>
              <v-btn
                v-if="auth.canPropose"
                color="primary"
                variant="tonal"
                :prepend-icon="auth.canDirectEdit ? 'mdi-plus' : 'mdi-file-plus-outline'"
                @click="itemOpen = true"
              >
                {{ auth.canDirectEdit ? $t('templates.newItem') : $t('items.proposeNew') }}
              </v-btn>
              <v-btn v-if="auth.canPropose" variant="tonal" prepend-icon="mdi-content-copy" @click="duplicateOpen = true">
                {{ $t('templates.duplicate') }}
              </v-btn>
              <v-btn v-if="auth.canPropose" color="primary" variant="flat" prepend-icon="mdi-pencil" @click="editorOpen = true">
                {{ auth.canDirectEdit ? $t('common.edit') : $t('templates.proposeEdit') }}
              </v-btn>
              <v-btn
                v-if="auth.canDirectEdit"
                variant="tonal"
                color="error"
                icon="mdi-delete-outline"
                :disabled="tpl.counts.total + tpl.counts.destroyed > 0"
                @click="deleteOpen = true"
              />
            </div>
          </div>
          <p v-if="tpl.description" class="text-body-2 mt-4 mb-0"><bdi>{{ tpl.description }}</bdi></p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <v-chip v-for="s in ACTIVE_STATES" :key="s" :color="STATE_COLORS[s]" size="small" variant="tonal">
              {{ STATE_LABELS[s] }} · {{ tpl.counts[s as 'built' | 'ok' | 'faulty'] }}
            </v-chip>
          </div>
        </v-card-text>
      </v-card>

      <v-card variant="flat" border>
        <v-tabs v-model="tab" color="primary" show-arrows>
          <v-tab value="fields" prepend-icon="mdi-form-select">{{ $t('templates.tabs.fields') }}</v-tab>
          <v-tab value="relations" prepend-icon="mdi-file-tree-outline">{{ $t('templates.tabs.relations') }}</v-tab>
          <v-tab value="graph" prepend-icon="mdi-graph-outline">{{ $t('templates.tabs.graph') }}</v-tab>
          <v-tab value="history" prepend-icon="mdi-history">{{ $t('templates.tabs.history') }}</v-tab>
        </v-tabs>
        <v-divider />
        <v-window v-model="tab">
          <v-window-item value="fields" class="pa-4">
            <div class="d-flex flex-wrap align-center gap-4 mb-3 text-caption">
              <span class="d-flex align-center gap-1"><span class="sw sw-white" /> {{ $t('tplEditor.legendWhite') }}</span>
              <span class="d-flex align-center gap-1"><span class="sw sw-white"><v-icon icon="mdi-menu-down" size="12" /></span> {{ $t('tplEditor.legendList') }}</span>
              <span class="d-flex align-center gap-1"><span class="sw sw-grey" /> {{ $t('tplEditor.legendGrey') }}</span>
              <span class="d-flex align-center gap-1"><strong class="text-error">*</strong> {{ $t('tplEditor.legendRequired') }}</span>
            </div>
            <v-table v-if="tpl.fields.length" class="border rounded" density="comfortable">
              <thead>
                <tr>
                  <th>{{ $t('tplEditor.fieldName') }}</th>
                  <th>{{ $t('fields.type') }}</th>
                  <th>{{ $t('templates.mode') }}</th>
                  <th>{{ $t('templates.valueOrList') }}</th>
                  <th>{{ $t('templates.format') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="f in tpl.fields" :key="f.id" :class="f.mode === 'item' ? 'row-grey' : 'row-white'">
                  <td class="font-weight-medium">
                    <bdi>{{ fieldLabel(f) }}</bdi><span v-if="f.required" class="text-error ms-1">*</span>
                    <v-icon v-if="f.mode === 'choice' || f.field_type === 'enum'" icon="mdi-menu-down" size="16" />
                  </td>
                  <td>
                    <v-icon :icon="FIELD_TYPE_ICONS[f.field_type]" size="16" class="me-1 text-medium-emphasis" />
                    {{ FIELD_TYPE_LABELS[f.field_type] }}
                  </td>
                  <td>{{ FIELD_MODE_LABELS[f.mode] }}</td>
                  <td>
                    <template v-if="f.field_type === 'files' && f.mode === 'fixed'">
                      <div class="d-flex flex-wrap gap-1 align-center py-1">
                        <v-chip
                          v-for="d in f.files"
                          :key="d.id"
                          size="small"
                          prepend-icon="mdi-paperclip"
                          :closable="auth.canDirectEdit"
                          @click="downloadDoc(d)"
                          @click:close="removeTemplateFile(d)"
                        >
                          <bdi>{{ d.name }}</bdi> <span class="text-medium-emphasis ms-1">{{ formatBytes(d.size_bytes) }}</span>
                        </v-chip>
                        <v-file-input
                          v-if="auth.canDirectEdit"
                          :model-value="[]"
                          multiple
                          density="compact"
                          hide-details
                          prepend-icon="mdi-upload"
                          variant="plain"
                          style="max-width: 44px"
                          :loading="uploadingField === f.id"
                          @update:model-value="(v: File | File[]) => uploadTemplateFiles(f, v)"
                        />
                      </div>
                    </template>
                    <span v-else>{{ shown(f) }}</span>
                  </td>
                  <td class="text-medium-emphasis">{{ formatOf(f) }}</td>
                </tr>
              </tbody>
            </v-table>
            <EmptyState v-else icon="mdi-form-select" :title="$t('templates.noFields')" />
          </v-window-item>

          <v-window-item value="relations" class="pa-4">
            <v-row>
              <v-col cols="12" md="6">
                <div class="text-overline text-medium-emphasis mb-2">{{ $t('templates.contains') }}</div>
                <div v-if="tpl.children.length" class="d-flex flex-wrap gap-2">
                  <v-chip
                    v-for="c in tpl.children"
                    :key="c.template.id"
                    :to="`/templates/${c.template.id}`"
                    variant="tonal"
                    color="primary"
                  >
                    <TypeIcon :type="c.template.type" :size="16" class="me-1" /> <bdi>{{ c.template.name }}</bdi>
                    <span v-if="limitLabel(c.min_count, c.max_count)" class="text-caption ms-2 opacity-80">
                      {{ limitLabel(c.min_count, c.max_count) }}
                    </span>
                  </v-chip>
                </div>
                <div v-else class="text-medium-emphasis text-body-2">{{ $t('templates.noChildren') }}</div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="text-overline text-medium-emphasis mb-2">{{ $t('templates.usedIn') }}</div>
                <div v-if="tpl.parent_templates.length" class="d-flex flex-wrap gap-2">
                  <v-chip
                    v-for="p in tpl.parent_templates"
                    :key="p.id"
                    :to="`/templates/${p.id}`"
                    variant="tonal"
                  >
                    <TypeIcon :type="p.type" :size="16" class="me-1" /> <bdi>{{ p.name }}</bdi>
                  </v-chip>
                </div>
                <div v-else class="text-medium-emphasis text-body-2">{{ $t('templates.noParents') }}</div>
              </v-col>
            </v-row>
          </v-window-item>

          <v-window-item value="graph" class="pa-4">
            <HierarchyGraph
              :data="graph"
              kind="templates"
              height="520px"
              :focus-id="tpl.id"
              @node-click="onGraphClick"
            />
          </v-window-item>

          <v-window-item value="history" class="pa-4">
            <v-timeline v-if="audit.length" side="end" align="start" density="compact" truncate-line="both">
              <v-timeline-item v-for="a in audit" :key="a.id" dot-color="primary" size="x-small">
                <template #opposite>
                  <span class="text-caption text-medium-emphasis">{{ formatDateTime(a.created_at) }}</span>
                </template>
                <div class="font-weight-medium"><bdi>{{ a.summary }}</bdi></div>
                <div v-if="a.user_name" class="text-caption">— <bdi>{{ a.user_name }}</bdi></div>
              </v-timeline-item>
            </v-timeline>
            <EmptyState v-else icon="mdi-history" :title="$t('audit.noRecords')" />
          </v-window-item>
        </v-window>
      </v-card>

      <TemplateEditorDialog v-model="editorOpen" :template="tpl" :direct="auth.canDirectEdit" @submit="onEditSubmit" />
      <TemplateEditorDialog
        v-model="duplicateOpen"
        :duplicate-from="tpl"
        :direct="auth.canDirectEdit"
        @submit="onDuplicateSubmit"
      />
      <ItemFormDialog
        v-model="itemOpen"
        mode="create"
        :type="tpl.type"
        :template-id="tpl.id"
        :direct="auth.canDirectEdit"
        @saved="onItemSaved"
        @propose="onItemPropose"
      />
      <ProposeChangeDialog v-model="proposeOpen" :context="proposeCtx" />
      <ConfirmDialog
        v-model="deleteOpen"
        :title="$t('templates.deleteTitle')"
        :message="$t('templates.deleteMsg', { name: tpl.name })"
        :confirm-text="$t('common.delete')"
        color="error"
        icon="mdi-delete-alert"
        :loading="deleting"
        @confirm="remove"
      />
    </template>

    <EmptyState v-else icon="mdi-alert-circle-outline" :title="$t('templates.notFound')" />
  </v-container>
</template>

<style scoped>
.row-grey td {
  background: rgba(var(--v-theme-on-surface), 0.05);
}
.sw {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 16px;
  border-radius: 4px;
  border: 1px solid rgba(var(--v-border-color), 0.4);
}
.sw-white {
  background: rgb(var(--v-theme-surface));
}
.sw-grey {
  background: rgba(var(--v-theme-on-surface), 0.12);
}
</style>
