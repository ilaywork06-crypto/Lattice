<script setup lang="ts">
// Excel import/export, one sheet per template.
//
// The import file has a sheet for each template whose header row is exactly
// the fields filled in when an item is created from it. Importing is
// all-or-nothing: if any cell is invalid nothing is saved, and every bad cell
// is listed (sheet + cell + reason) so the file can be fixed in one pass.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { extractError, extractErrorList, type ApiErrorEntry } from '@/api/client'
import { dataApi, templatesApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import { downloadBlob } from '@/utils/download'
import { ITEM_TYPES, TYPE_LABELS } from '@/constants'
import type { ImportResult, ItemType, TemplateSummary } from '@/api/types'

const auth = useAuthStore()
const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

const templates = ref<TemplateSummary[]>([])

// A scope is "every template", one item type, or one template.
type Scope = { kind: 'all' } | { kind: 'type'; type: ItemType } | { kind: 'template'; id: number }
const NAV_PLURAL: Record<ItemType, string> = {
  setup: 'nav.setups',
  assembly: 'nav.assemblies',
  card: 'nav.cards',
}

const scopeItems = computed(() => [
  { title: t('impexp.allTemplates'), value: 'all', props: { prependIcon: 'mdi-select-all' } },
  ...ITEM_TYPES.map((ty) => ({
    title: t('impexp.allOfType', { type: t(NAV_PLURAL[ty]) }),
    value: `type:${ty}`,
    props: { prependIcon: 'mdi-shape-outline' },
  })),
  ...templates.value.map((tp) => ({
    title: tp.name,
    value: `tpl:${tp.id}`,
    props: { subtitle: `${TYPE_LABELS[tp.type]} · ${tp.serial_prefix}` },
  })),
])

function parseScope(v: string): Scope {
  if (v.startsWith('type:')) return { kind: 'type', type: v.slice(5) as ItemType }
  if (v.startsWith('tpl:')) return { kind: 'template', id: Number(v.slice(4)) }
  return { kind: 'all' }
}
function params(v: string) {
  const s = parseScope(v)
  if (s.kind === 'type') return { type: s.type }
  if (s.kind === 'template') return { template_id: s.id }
  return {}
}
function fileName(prefix: string, v: string): string {
  const s = parseScope(v)
  const suffix =
    s.kind === 'type'
      ? `_${s.type}`
      : s.kind === 'template'
        ? `_${templates.value.find((x) => x.id === s.id)?.serial_prefix ?? s.id}`
        : ''
  return `lattice_${prefix}${suffix}.xlsx`
}

const templateScope = ref('all')
const exportScope = ref('all')
const downloadingTemplate = ref(false)
const exporting = ref(false)

async function downloadTemplate() {
  downloadingTemplate.value = true
  try {
    downloadBlob(await dataApi.template(params(templateScope.value)), fileName('import', templateScope.value))
    ui.success(t('impexp.templateDownloaded'))
  } catch (e) {
    ui.error(e)
  } finally {
    downloadingTemplate.value = false
  }
}

async function exportData() {
  exporting.value = true
  try {
    downloadBlob(await dataApi.export(params(exportScope.value)), fileName('export', exportScope.value))
    ui.success(t('impexp.exportDownloaded'))
  } catch (e) {
    ui.error(e)
  } finally {
    exporting.value = false
  }
}

// ── import ──
// v-file-input without `multiple` hands back a single File (Vuetify 3.x), not
// an array — reading `[0]` of it was why every import said "choose a file".
const file = ref<File | File[] | null>(null)
const importing = ref(false)
const result = ref<ImportResult | null>(null)
const failure = ref<{ message: string; errors: ApiErrorEntry[] } | null>(null)

const chosenFile = computed<File | null>(() =>
  Array.isArray(file.value) ? file.value[0] ?? null : file.value,
)

const errorHeaders = computed(() => [
  { title: t('impexp.sheet'), key: 'sheet' },
  { title: t('impexp.cell'), key: 'cell', width: 90 },
  { title: t('impexp.column'), key: 'column' },
  { title: t('impexp.error'), key: 'error' },
])

async function runImport() {
  const f = chosenFile.value
  if (!f) {
    ui.warning(t('impexp.chooseFirst'))
    return
  }
  importing.value = true
  result.value = null
  failure.value = null
  try {
    result.value = await dataApi.import(f)
    ui.success(t('impexp.importedOk', { created: result.value.created }))
    file.value = null
    await loadTemplates()
  } catch (e) {
    failure.value = { message: extractError(e), errors: extractErrorList(e) }
    ui.error(e)
  } finally {
    importing.value = false
  }
}

async function loadTemplates() {
  try {
    templates.value = await templatesApi.list()
  } catch (e) {
    ui.error(e)
  }
}

onMounted(loadTemplates)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader :title="$t('nav.importExport')" :subtitle="$t('impexp.subtitle')" icon="mdi-swap-vertical-bold" />

    <v-row>
      <!-- 1. import file -->
      <v-col cols="12" md="4">
        <v-card variant="flat" border height="100%">
          <v-card-item>
            <template #prepend>
              <v-avatar color="info" variant="tonal" rounded="lg"><v-icon icon="mdi-file-download-outline" /></v-avatar>
            </template>
            <v-card-title>{{ $t('impexp.step1Title') }}</v-card-title>
            <v-card-subtitle>{{ $t('impexp.step1Sub') }}</v-card-subtitle>
          </v-card-item>
          <v-card-text>
            <v-autocomplete v-model="templateScope" :label="$t('impexp.scope')" :items="scopeItems" class="mb-2" />
            <v-btn block color="info" variant="tonal" prepend-icon="mdi-download" :loading="downloadingTemplate" @click="downloadTemplate">
              {{ $t('impexp.downloadTemplate') }}
            </v-btn>
            <div class="text-caption text-medium-emphasis mt-3">{{ $t('impexp.templateExplainer') }}</div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- 2. import -->
      <v-col cols="12" md="4">
        <v-card variant="flat" border height="100%">
          <v-card-item>
            <template #prepend>
              <v-avatar color="primary" variant="tonal" rounded="lg"><v-icon icon="mdi-file-upload-outline" /></v-avatar>
            </template>
            <v-card-title>{{ $t('impexp.step2Title') }}</v-card-title>
            <v-card-subtitle>{{ $t('impexp.step2Sub') }}</v-card-subtitle>
          </v-card-item>
          <v-card-text>
            <template v-if="auth.canDirectEdit">
              <v-file-input
                v-model="file"
                :label="$t('impexp.selectFile')"
                accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                prepend-icon=""
                prepend-inner-icon="mdi-paperclip"
                show-size
                class="mb-2"
              />
              <v-btn block color="primary" prepend-icon="mdi-upload" :loading="importing" :disabled="!chosenFile" @click="runImport">
                {{ $t('impexp.importBtn') }}
              </v-btn>
              <div class="text-caption text-medium-emphasis mt-3">{{ $t('impexp.allOrNothing') }}</div>
            </template>
            <v-alert v-else type="info" variant="tonal" density="compact">{{ $t('impexp.managersOnly') }}</v-alert>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- export -->
      <v-col cols="12" md="4">
        <v-card variant="flat" border height="100%">
          <v-card-item>
            <template #prepend>
              <v-avatar color="success" variant="tonal" rounded="lg"><v-icon icon="mdi-microsoft-excel" /></v-avatar>
            </template>
            <v-card-title>{{ $t('impexp.exportTitle') }}</v-card-title>
            <v-card-subtitle>{{ $t('impexp.exportSub') }}</v-card-subtitle>
          </v-card-item>
          <v-card-text>
            <v-autocomplete v-model="exportScope" :label="$t('impexp.scope')" :items="scopeItems" class="mb-2" />
            <v-btn block color="success" variant="tonal" prepend-icon="mdi-download" :loading="exporting" @click="exportData">
              {{ $t('impexp.exportBtn') }}
            </v-btn>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- results -->
    <v-card v-if="result" variant="flat" border class="mt-6">
      <v-card-title class="d-flex align-center gap-2">
        <v-icon icon="mdi-check-circle" color="success" />
        {{ $t('impexp.resultsTitle') }}
        <v-chip color="success" variant="tonal" size="small">{{ $t('impexp.created', { n: result.created }) }}</v-chip>
      </v-card-title>
      <v-divider />
      <v-table density="compact">
        <tbody>
          <tr v-for="(n, name) in result.by_template" :key="name">
            <td>{{ name }}</td>
            <td class="text-end font-weight-medium">{{ n }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <v-card v-if="failure" variant="flat" border class="mt-6">
      <v-card-title class="d-flex align-center gap-2">
        <v-icon icon="mdi-alert-circle" color="error" />
        {{ $t('impexp.failedTitle') }}
        <v-chip color="error" variant="tonal" size="small">{{ $t('impexp.errors', { n: failure.errors.length || 1 }) }}</v-chip>
      </v-card-title>
      <v-card-subtitle class="pb-2">{{ failure.message }}</v-card-subtitle>
      <v-divider />
      <v-data-table
        v-if="failure.errors.length"
        :headers="errorHeaders as any"
        :items="failure.errors"
        density="compact"
        :items-per-page="50"
      >
        <template #item.cell="{ item }">
          <v-chip v-if="item.cell" size="x-small" color="error" variant="tonal" label class="font-weight-bold">{{ item.cell }}</v-chip>
          <span v-else class="text-medium-emphasis">{{ item.row ? $t('impexp.rowN', { n: item.row }) : '—' }}</span>
        </template>
      </v-data-table>
    </v-card>
  </v-container>
</template>
