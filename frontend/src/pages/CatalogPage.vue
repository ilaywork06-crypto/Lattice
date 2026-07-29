<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { catalogApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import { useCatalogStore } from '@/stores/catalog'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import type { CatalogCategory, CatalogOption } from '@/api/types'

const { t } = useI18n({ useScope: 'global' })
const ui = useUiStore()
const catalog = useCatalogStore()

const category = ref<CatalogCategory>('project')
const options = ref<CatalogOption[]>([])
const loading = ref(false)

const tabs = computed(() => [
  { value: 'project' as const, label: t('catalog.projects'), icon: 'mdi-folder-outline' },
  { value: 'industry' as const, label: t('catalog.industries'), icon: 'mdi-factory' },
])

const headers = computed(() => [
  { title: t('catalog.value'), key: 'value' },
  { title: t('catalog.description'), key: 'description', sortable: false },
  { title: t('catalog.usage'), key: 'usage_count', align: 'center', width: 110 },
  { title: t('catalog.active'), key: 'active', align: 'center', width: 110 },
  { title: '', key: 'actions', sortable: false, align: 'end', width: 110 },
])

async function load() {
  loading.value = true
  try {
    options.value = await catalogApi.list(category.value)
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

watch(category, load)

// ---- Create / edit --------------------------------------------------------
const dialog = ref(false)
const editing = ref<CatalogOption | null>(null)
const saving = ref(false)
const form = reactive({ value: '', description: '', active: true, sort_order: 0 })

function openCreate() {
  editing.value = null
  Object.assign(form, { value: '', description: '', active: true, sort_order: options.value.length })
  dialog.value = true
}
function openEdit(opt: CatalogOption) {
  editing.value = opt
  Object.assign(form, {
    value: opt.value,
    description: opt.description ?? '',
    active: opt.active,
    sort_order: opt.sort_order,
  })
  dialog.value = true
}

async function save() {
  if (!form.value.trim()) {
    ui.warning(t('catalog.valueRequired'))
    return
  }
  saving.value = true
  const body = {
    value: form.value.trim(),
    description: form.description.trim() || null,
    active: form.active,
    sort_order: Number(form.sort_order) || 0,
  }
  try {
    if (editing.value) {
      await catalogApi.update(editing.value.id, body)
      ui.success(t('catalog.updated'))
    } else {
      await catalogApi.create({ category: category.value, ...body })
      ui.success(t('catalog.created'))
    }
    dialog.value = false
    await load()
    await catalog.refresh()
  } catch (e) {
    ui.error(e)
  } finally {
    saving.value = false
  }
}

async function toggleActive(opt: CatalogOption) {
  try {
    await catalogApi.update(opt.id, { active: !opt.active })
    await load()
    await catalog.refresh()
  } catch (e) {
    ui.error(e)
  }
}

// ---- Delete ---------------------------------------------------------------
const removeOpt = ref<CatalogOption | null>(null)
async function confirmRemove() {
  if (!removeOpt.value) return
  try {
    await catalogApi.remove(removeOpt.value.id)
    ui.success(t('catalog.deleted'))
    await load()
    await catalog.refresh()
  } catch (e) {
    ui.error(e)
  } finally {
    removeOpt.value = null
  }
}

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader :title="$t('nav.catalog')" :subtitle="$t('catalog.subtitle')" icon="mdi-tag-multiple-outline">
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="load" />
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">
          {{ category === 'project' ? $t('catalog.addProject') : $t('catalog.addIndustry') }}
        </v-btn>
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-tabs v-model="category" color="primary">
        <v-tab v-for="tb in tabs" :key="tb.value" :value="tb.value" :prepend-icon="tb.icon">
          {{ tb.label }}
        </v-tab>
      </v-tabs>
      <v-divider />
      <v-alert type="info" variant="tonal" density="compact" class="ma-4" icon="mdi-information-outline">
        {{ $t('catalog.explainer') }}
      </v-alert>

      <v-data-table
        :headers="headers as any"
        :items="options"
        :loading="loading"
        item-value="id"
        density="comfortable"
        :items-per-page="25"
      >
        <template #item.value="{ item }">
          <span class="font-weight-medium">{{ item.value }}</span>
        </template>
        <template #item.description="{ item }">
          <span :class="{ 'text-medium-emphasis': !item.description }">{{ item.description || '—' }}</span>
        </template>
        <template #item.usage_count="{ item }">
          <v-chip size="x-small" variant="tonal" :color="item.usage_count ? 'primary' : undefined">
            {{ item.usage_count }}
          </v-chip>
        </template>
        <template #item.active="{ item }">
          <v-switch
            :model-value="item.active"
            color="success"
            density="compact"
            hide-details
            inset
            @update:model-value="toggleActive(item)"
          />
        </template>
        <template #item.actions="{ item }">
          <v-btn icon="mdi-pencil" size="small" variant="text" @click="openEdit(item)" />
          <v-btn
            icon="mdi-delete-outline"
            size="small"
            variant="text"
            color="error"
            :disabled="item.usage_count > 0"
            @click="removeOpt = item"
          />
        </template>
        <template #no-data>
          <EmptyState icon="mdi-tag-off-outline" :title="$t('catalog.empty')" :text="$t('catalog.emptyHint')" />
        </template>
      </v-data-table>
    </v-card>

    <!-- Create / edit dialog -->
    <v-dialog v-model="dialog" max-width="520">
      <v-card rounded="lg">
        <v-card-title class="pa-4">
          {{ editing ? $t('catalog.editOption') : (category === 'project' ? $t('catalog.addProject') : $t('catalog.addIndustry')) }}
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-text-field v-model="form.value" :label="$t('catalog.valueReq')" class="mb-1" autofocus />
          <v-text-field v-model="form.description" :label="$t('catalog.description')" class="mb-1" />
          <v-row dense align="center">
            <v-col cols="6">
              <v-text-field v-model.number="form.sort_order" :label="$t('catalog.sortOrder')" type="number" />
            </v-col>
            <v-col cols="6">
              <v-switch v-model="form.active" :label="$t('catalog.active')" color="success" hide-details inset />
            </v-col>
          </v-row>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="saving" @click="save">
            {{ editing ? $t('common.save') : $t('common.create') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ConfirmDialog
      :model-value="removeOpt !== null"
      :title="$t('catalog.deleteTitle')"
      :message="removeOpt ? $t('catalog.deleteMsg', { value: removeOpt.value }) : ''"
      :confirm-text="$t('common.delete')"
      color="error"
      @update:model-value="(v) => !v && (removeOpt = null)"
      @confirm="confirmRemove"
    />
  </v-container>
</template>
