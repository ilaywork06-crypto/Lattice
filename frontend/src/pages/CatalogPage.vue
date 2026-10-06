<script setup lang="ts">
// Admin catalogs: projects, industries and teams (each value can be linked,
// two-way and many-to-many, to values of the other two), plus the desiccator —
// the set of locations whose loose cards count as stock.
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { catalogApi, locationsApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import { useCatalogStore } from '@/stores/catalog'
import { useRefsStore } from '@/stores/refs'
import PageHeader from '@/components/PageHeader.vue'
import FieldGroupsPanel from '@/components/FieldGroupsPanel.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import type { CatalogCategory, CatalogOption, LocationOut } from '@/api/types'

const { t } = useI18n({ useScope: 'global' })
const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const catalog = useCatalogStore()
const refs = useRefsStore()

type Tab = CatalogCategory | 'desiccator' | 'field_groups'
const CATEGORIES: CatalogCategory[] = ['project', 'industry', 'team']
const tab = ref<Tab>((route.query.tab as Tab) || 'project')
const all = ref<CatalogOption[]>([])
const loading = ref(false)

const tabs = computed(() => [
  { value: 'project' as const, label: t('catalog.projects'), icon: 'mdi-folder-outline' },
  { value: 'industry' as const, label: t('catalog.industries'), icon: 'mdi-factory' },
  { value: 'team' as const, label: t('catalog.teams'), icon: 'mdi-account-group-outline' },
  { value: 'desiccator' as const, label: t('catalog.desiccator'), icon: 'mdi-water-off' },
  { value: 'field_groups' as const, label: t('fieldGroups.tab'), icon: 'mdi-form-select' },
])

const isCategory = computed(() => CATEGORIES.includes(tab.value as CatalogCategory))
const category = computed(() => (isCategory.value ? (tab.value as CatalogCategory) : 'project'))
const options = computed(() => all.value.filter((o) => o.category === category.value))
const otherCategories = computed(() => CATEGORIES.filter((c) => c !== category.value))
const byId = computed(() => new Map(all.value.map((o) => [o.id, o])))

const CAT_LABEL: Record<CatalogCategory, string> = {
  project: 'catalog.projects',
  industry: 'catalog.industries',
  team: 'catalog.teams',
}
const ADD_LABEL: Record<CatalogCategory, string> = {
  project: 'catalog.addProject',
  industry: 'catalog.addIndustry',
  team: 'catalog.addTeam',
}

const headers = computed(() => [
  { title: t('catalog.value'), key: 'value' },
  { title: t('catalog.description'), key: 'description', sortable: false },
  { title: t('catalog.links'), key: 'links', sortable: false },
  { title: t('catalog.usage'), key: 'usage_count', align: 'center', width: 100 },
  { title: t('catalog.active'), key: 'active', align: 'center', width: 100 },
  { title: '', key: 'actions', sortable: false, align: 'end', width: 150 },
])

function linkedOf(opt: CatalogOption, cat: CatalogCategory): CatalogOption[] {
  return opt.linked_ids.map((id) => byId.value.get(id)).filter((o): o is CatalogOption => !!o && o.category === cat)
}

async function load() {
  loading.value = true
  try {
    all.value = await catalogApi.list()
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

watch(tab, (v) => {
  router.replace({ query: { ...route.query, tab: v } })
  if (v === 'desiccator') void loadLocations()
})

// ── create / edit ──
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

// ── links (two-way) ──
const linksOpen = ref(false)
const linksFor = ref<CatalogOption | null>(null)
const linkSel = reactive<Record<CatalogCategory, number[]>>({ project: [], industry: [], team: [] })
const linksSaving = ref(false)

function openLinks(opt: CatalogOption) {
  linksFor.value = opt
  for (const c of CATEGORIES) linkSel[c] = linkedOf(opt, c).map((o) => o.id)
  linksOpen.value = true
}

async function saveLinks() {
  if (!linksFor.value) return
  linksSaving.value = true
  try {
    for (const c of otherCategories.value) {
      await catalogApi.setLinks(linksFor.value.id, c, linkSel[c])
    }
    ui.success(t('catalog.linksSaved'))
    linksOpen.value = false
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    linksSaving.value = false
  }
}

// ── delete ──
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

// ── desiccator ──
const locations = ref<LocationOut[]>([])
const desiccatorIds = ref<number[]>([])
const locLoading = ref(false)
const locSaving = ref(false)
const locSearch = ref('')

async function loadLocations() {
  locLoading.value = true
  try {
    locations.value = await locationsApi.list()
    desiccatorIds.value = locations.value.filter((l) => l.is_desiccator).map((l) => l.id)
  } catch (e) {
    ui.error(e)
  } finally {
    locLoading.value = false
  }
}

const desiccatorDirty = computed(() => {
  const before = locations.value.filter((l) => l.is_desiccator).map((l) => l.id).sort()
  return JSON.stringify(before) !== JSON.stringify([...desiccatorIds.value].sort())
})

async function saveDesiccator() {
  locSaving.value = true
  try {
    locations.value = await locationsApi.setDesiccator(desiccatorIds.value)
    desiccatorIds.value = locations.value.filter((l) => l.is_desiccator).map((l) => l.id)
    await refs.refreshLocations()
    ui.success(t('catalog.desiccatorSaved'))
  } catch (e) {
    ui.error(e)
  } finally {
    locSaving.value = false
  }
}

const locHeaders = computed(() => [
  { title: t('fields.location'), key: 'name' },
  { title: t('loc.colBuilding'), key: 'building' },
  { title: t('loc.colRoom'), key: 'room' },
  { title: t('loc.colItems'), key: 'item_count', align: 'center', width: 100 },
])

const groupsPanel = ref<{ load: () => Promise<void> } | null>(null)
function refresh() {
  void load()
  if (tab.value === 'desiccator') void loadLocations()
  if (tab.value === 'field_groups') void groupsPanel.value?.load()
}

onMounted(async () => {
  await load()
  if (tab.value === 'desiccator') await loadLocations()
})
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader :title="$t('nav.catalog')" :subtitle="$t('catalog.subtitle')" icon="mdi-tag-multiple-outline">
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="refresh" />
        <v-btn v-if="isCategory" color="primary" prepend-icon="mdi-plus" @click="openCreate">
          {{ $t(ADD_LABEL[category]) }}
        </v-btn>
        <v-btn
          v-else-if="tab === 'desiccator'"
          color="primary"
          prepend-icon="mdi-content-save"
          :disabled="!desiccatorDirty"
          :loading="locSaving"
          @click="saveDesiccator"
        >
          {{ $t('common.save') }}
        </v-btn>
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-tabs v-model="tab" color="primary" show-arrows>
        <v-tab v-for="tb in tabs" :key="tb.value" :value="tb.value" :prepend-icon="tb.icon">
          <bdi>{{ tb.label }}</bdi>
        </v-tab>
      </v-tabs>
      <v-divider />

      <template v-if="isCategory">
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
            <span class="font-weight-medium"><bdi>{{ item.value }}</bdi></span>
          </template>
          <template #item.description="{ item }">
            <span :class="{ 'text-medium-emphasis': !item.description }">{{ item.description || '—' }}</span>
          </template>
          <template #item.links="{ item }">
            <div class="d-flex flex-column gap-1 py-1">
              <div v-for="c in otherCategories" :key="c" class="d-flex flex-wrap align-center gap-1">
                <span class="text-caption text-medium-emphasis me-1">{{ $t(CAT_LABEL[c]) }}:</span>
                <v-chip v-for="o in linkedOf(item, c)" :key="o.id" size="x-small" variant="tonal" color="primary">
                  <bdi>{{ o.value }}</bdi>
                </v-chip>
                <span v-if="!linkedOf(item, c).length" class="text-caption text-medium-emphasis">—</span>
              </div>
            </div>
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
            <v-btn icon="mdi-link-variant" size="small" variant="text" :title="$t('catalog.editLinks')" @click="openLinks(item)" />
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
      </template>

      <!-- field groups: reusable sets of template fields -->
      <FieldGroupsPanel v-else-if="tab === 'field_groups'" ref="groupsPanel" />

      <!-- desiccator: which locations count as stock -->
      <template v-else>
        <v-alert type="info" variant="tonal" density="compact" class="ma-4" icon="mdi-water-off">
          {{ $t('catalog.desiccatorExplainer') }}
        </v-alert>
        <div class="px-4 pb-2 d-flex align-center gap-3 flex-wrap">
          <v-chip color="cyan-darken-2" variant="tonal">
            {{ $t('catalog.desiccatorCount', { n: desiccatorIds.length }) }}
          </v-chip>
          <v-spacer />
          <v-text-field
            v-model="locSearch"
            :label="$t('common.search')"
            prepend-inner-icon="mdi-magnify"
            clearable
            hide-details
            density="comfortable"
            style="max-width: 280px"
          />
        </div>
        <v-data-table
          v-model="desiccatorIds"
          :headers="locHeaders as any"
          :items="locations"
          :loading="locLoading"
          :search="locSearch"
          item-value="id"
          show-select
          density="comfortable"
          :items-per-page="25"
        >
          <template #item.name="{ item }">
            <span class="font-weight-medium"><bdi>{{ item.name }}</bdi></span>
          </template>
          <template #item.building="{ item }">{{ item.building || '—' }}</template>
          <template #item.room="{ item }">{{ item.room || '—' }}</template>
          <template #no-data>
            <EmptyState icon="mdi-map-marker-off" :title="$t('loc.noLocations')" />
          </template>
        </v-data-table>
      </template>
    </v-card>

    <!-- create / edit value -->
    <v-dialog v-model="dialog" max-width="520">
      <v-card rounded="lg">
        <v-card-title class="pa-4">
          {{ editing ? $t('catalog.editOption') : $t(ADD_LABEL[category]) }}
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

    <!-- links -->
    <v-dialog v-model="linksOpen" max-width="560">
      <v-card v-if="linksFor" rounded="lg">
        <v-card-title class="pa-4">{{ $t('catalog.linksOf', { value: linksFor.value }) }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-alert type="info" variant="tonal" density="compact" class="mb-4">{{ $t('catalog.linksHint') }}</v-alert>
          <v-autocomplete
            v-for="c in otherCategories"
            :key="c"
            v-model="linkSel[c]"
            :label="$t(CAT_LABEL[c])"
            :items="all.filter((o) => o.category === c).map((o) => ({ title: o.value, value: o.id }))"
            multiple
            chips
            closable-chips
          />
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-spacer />
          <v-btn variant="text" @click="linksOpen = false">{{ $t('common.cancel') }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="linksSaving" @click="saveLinks">{{ $t('common.save') }}</v-btn>
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
