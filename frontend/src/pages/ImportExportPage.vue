<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { dataApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import { downloadBlob } from '@/utils/download'
import { ITEM_TYPES } from '@/constants'
import type { ImportResult, ItemType } from '@/api/types'

const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

const templateType = ref<ItemType | null>(null)
const exportType = ref<ItemType | null>(null)
const downloadingTemplate = ref(false)
const exporting = ref(false)

const NAV_PLURAL: Record<ItemType, string> = { setup: 'nav.setups', assembly: 'nav.assemblies', card: 'nav.cards' }
const typeItems = computed(() => [
  { title: t('impexp.allTypes'), value: null },
  ...ITEM_TYPES.map((ty) => ({ title: t(NAV_PLURAL[ty]), value: ty })),
])

function fileLabel(prefix: string, type: ItemType | null): string {
  return `lattice_${prefix}${type ? `_${type}` : ''}.xlsx`
}

async function downloadTemplate() {
  downloadingTemplate.value = true
  try {
    const blob = await dataApi.template(templateType.value ?? undefined)
    downloadBlob(blob, fileLabel('template', templateType.value))
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
    const blob = await dataApi.export(exportType.value ?? undefined)
    downloadBlob(blob, fileLabel('export', exportType.value))
    ui.success(t('impexp.exportDownloaded'))
  } catch (e) {
    ui.error(e)
  } finally {
    exporting.value = false
  }
}

// ---- Import ---------------------------------------------------------------
const file = ref<File[]>([])
const importing = ref(false)
const result = ref<ImportResult | null>(null)

async function runImport() {
  const f = file.value?.[0]
  if (!f) {
    ui.warning(t('impexp.chooseFirst'))
    return
  }
  importing.value = true
  result.value = null
  try {
    result.value = await dataApi.import(f)
    if (result.value.errors.length) {
      ui.warning(t('impexp.importedWithErrors', { created: result.value.created, errors: result.value.errors.length }))
    } else {
      ui.success(t('impexp.importedOk', { created: result.value.created }))
    }
  } catch (e) {
    ui.error(e)
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader
      :title="$t('nav.importExport')"
      :subtitle="$t('impexp.subtitle')"
      icon="mdi-swap-vertical-bold"
    />

    <v-row>
      <!-- Template -->
      <v-col cols="12" md="4">
        <v-card variant="flat" border height="100%">
          <v-card-item>
            <template #prepend>
              <v-avatar color="info" variant="tonal" rounded="lg">
                <v-icon icon="mdi-file-download-outline" />
              </v-avatar>
            </template>
            <v-card-title>{{ $t('impexp.step1Title') }}</v-card-title>
            <v-card-subtitle>{{ $t('impexp.step1Sub') }}</v-card-subtitle>
          </v-card-item>
          <v-card-text>
            <v-select v-model="templateType" :label="$t('impexp.type')" :items="typeItems" class="mb-2" />
            <v-btn
              block
              color="info"
              variant="tonal"
              prepend-icon="mdi-download"
              :loading="downloadingTemplate"
              @click="downloadTemplate"
            >
              {{ $t('impexp.downloadTemplate') }}
            </v-btn>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Import -->
      <v-col cols="12" md="4">
        <v-card variant="flat" border height="100%">
          <v-card-item>
            <template #prepend>
              <v-avatar color="primary" variant="tonal" rounded="lg">
                <v-icon icon="mdi-file-upload-outline" />
              </v-avatar>
            </template>
            <v-card-title>{{ $t('impexp.step2Title') }}</v-card-title>
            <v-card-subtitle>{{ $t('impexp.step2Sub') }}</v-card-subtitle>
          </v-card-item>
          <v-card-text>
            <v-file-input
              v-model="file"
              :label="$t('impexp.selectFile')"
              accept=".xlsx"
              prepend-icon=""
              prepend-inner-icon="mdi-paperclip"
              variant="outlined"
              density="comfortable"
              show-size
              class="mb-2"
            />
            <v-btn
              block
              color="primary"
              variant="flat"
              prepend-icon="mdi-upload"
              :loading="importing"
              @click="runImport"
            >
              {{ $t('impexp.importBtn') }}
            </v-btn>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Export -->
      <v-col cols="12" md="4">
        <v-card variant="flat" border height="100%">
          <v-card-item>
            <template #prepend>
              <v-avatar color="success" variant="tonal" rounded="lg">
                <v-icon icon="mdi-database-export-outline" />
              </v-avatar>
            </template>
            <v-card-title>{{ $t('impexp.exportTitle') }}</v-card-title>
            <v-card-subtitle>{{ $t('impexp.exportSub') }}</v-card-subtitle>
          </v-card-item>
          <v-card-text>
            <v-select v-model="exportType" :label="$t('impexp.type')" :items="typeItems" class="mb-2" />
            <v-btn
              block
              color="success"
              variant="tonal"
              prepend-icon="mdi-download"
              :loading="exporting"
              @click="exportData"
            >
              {{ $t('impexp.exportBtn') }}
            </v-btn>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Import results -->
    <v-card v-if="result" variant="flat" border class="mt-6">
      <v-card-title class="d-flex align-center gap-2">
        <v-icon icon="mdi-clipboard-check-outline" color="primary" />
        <span class="text-subtitle-1 font-weight-bold">{{ $t('impexp.resultsTitle') }}</span>
      </v-card-title>
      <v-divider />
      <v-card-text>
        <div class="d-flex flex-wrap gap-4 mb-2">
          <v-chip color="success" variant="tonal" prepend-icon="mdi-check">
            {{ $t('impexp.created', { n: result.created }) }}
          </v-chip>
          <v-chip
            :color="result.errors.length ? 'error' : 'success'"
            variant="tonal"
            prepend-icon="mdi-alert-circle-outline"
          >
            {{ $t('impexp.errors', { n: result.errors.length }) }}
          </v-chip>
        </div>
        <v-table v-if="result.errors.length" density="compact" class="border rounded mt-2">
          <thead>
            <tr>
              <th style="width: 90px">{{ $t('impexp.row') }}</th>
              <th>{{ $t('impexp.error') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(err, i) in result.errors" :key="i">
              <td>
                <v-chip size="x-small" color="error" variant="tonal">{{ err.row }}</v-chip>
              </td>
              <td class="text-error">{{ err.error }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
    </v-card>
  </v-container>
</template>
