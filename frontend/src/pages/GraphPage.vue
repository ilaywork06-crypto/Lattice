<script setup lang="ts">
// Hierarchy graphs that stay readable as the system grows.
//
// * "By template" (default) draws the hierarchy the templates define — which
//   setups hold which assemblies and cards. Small and stable however many units
//   exist. Narrow it to one template's subtree with the selector.
// * "Built units" draws every live tree made from one chosen template (pick a
//   setup or assembly type, see all of its units' trees). Clicking a template in
//   the first view opens it here.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { graphApi, templatesApi } from '@/api/services'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import HierarchyGraph from '@/components/HierarchyGraph.vue'
import {
  GRAPH_STATE_BORDER,
  GRAPH_TYPE_FILL,
  ITEM_STATES,
  ITEM_TYPES,
  STATE_LABELS,
  TYPE_LABELS,
} from '@/constants'
import type { GraphNode, GraphOut, TemplateSummary } from '@/api/types'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const { t } = useI18n({ useScope: 'global' })

type Mode = 'templates' | 'units'
const mode = ref<Mode>((route.query.mode as Mode) || 'templates')
const rootTemplateId = ref<number | null>(route.query.root ? Number(route.query.root) : null)
const unitsTemplateId = ref<number | null>(route.query.template ? Number(route.query.template) : null)
const templates = ref<TemplateSummary[]>([])
const data = ref<GraphOut | null>(null)
const loading = ref(false)

const containerTemplates = computed(() =>
  templates.value.filter((tp) => tp.type !== 'card' || tp.parent_template_ids.length === 0),
)
const templateChoices = (list: TemplateSummary[]) =>
  list.map((tp) => ({
    title: tp.name,
    value: tp.id,
    subtitle: `${TYPE_LABELS[tp.type]} · ${tp.serial_prefix} · ${t('graph.units', { n: tp.counts.total })}`,
  }))

async function loadTemplates() {
  try {
    templates.value = await templatesApi.list()
  } catch (e) {
    ui.error(e)
  }
}

async function load() {
  loading.value = true
  try {
    if (mode.value === 'templates') {
      data.value = await graphApi.templates(rootTemplateId.value)
    } else if (unitsTemplateId.value) {
      data.value = await graphApi.byTemplate(unitsTemplateId.value)
    } else {
      data.value = { nodes: [], edges: [], roots: [] }
    }
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

function syncQuery() {
  router.replace({
    query: {
      mode: mode.value,
      ...(rootTemplateId.value ? { root: String(rootTemplateId.value) } : {}),
      ...(unitsTemplateId.value ? { template: String(unitsTemplateId.value) } : {}),
    },
  })
}

watch([mode, rootTemplateId, unitsTemplateId], () => {
  syncQuery()
  void load()
})

function onNodeClick(node: GraphNode) {
  if (mode.value === 'templates') {
    unitsTemplateId.value = node.id
    mode.value = 'units'
  } else {
    router.push(`/items/${node.id}`)
  }
}

const nodeCount = computed(() => data.value?.nodes.length ?? 0)
const treeCount = computed(() => data.value?.roots.length ?? 0)

onMounted(async () => {
  await loadTemplates()
  if (mode.value === 'units' && !unitsTemplateId.value) {
    unitsTemplateId.value = templates.value.find((tp) => tp.type === 'setup')?.id ?? null
  }
  await load()
})
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader :title="$t('nav.graph')" :subtitle="$t('graph.subtitle')" icon="mdi-graph-outline">
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="load" />
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-card-text class="d-flex flex-wrap align-center gap-3">
        <v-btn-toggle v-model="mode" mandatory color="primary" variant="outlined" density="comfortable" rounded="lg">
          <v-btn value="templates" prepend-icon="mdi-shape-outline">{{ $t('graph.byTemplate') }}</v-btn>
          <v-btn value="units" prepend-icon="mdi-sitemap-outline">{{ $t('graph.builtUnits') }}</v-btn>
        </v-btn-toggle>
        <v-autocomplete
          v-if="mode === 'templates'"
          v-model="rootTemplateId"
          :label="$t('graph.rootTemplate')"
          :items="templateChoices(containerTemplates)"
          item-title="title"
          item-value="value"
          clearable
          hide-details
          density="comfortable"
          style="min-width: 280px; max-width: 420px"
          :placeholder="$t('graph.allTemplates')"
          persistent-placeholder
        >
          <template #item="{ props: itemProps, item }">
            <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
          </template>
        </v-autocomplete>
        <v-autocomplete
          v-else
          v-model="unitsTemplateId"
          :label="$t('graph.chooseTemplate')"
          :items="templateChoices(templates)"
          item-title="title"
          item-value="value"
          hide-details
          density="comfortable"
          style="min-width: 280px; max-width: 420px"
        >
          <template #item="{ props: itemProps, item }">
            <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
          </template>
        </v-autocomplete>
        <v-spacer />
        <v-chip size="small" variant="tonal" color="primary">{{ $t('graph.nodes', { n: nodeCount }) }}</v-chip>
        <v-chip v-if="mode === 'units'" size="small" variant="tonal">{{ $t('graph.trees', { n: treeCount }) }}</v-chip>
      </v-card-text>
      <v-divider />
      <div class="graph-toolbar">
        <div class="d-flex align-center gap-2" v-for="ty in ITEM_TYPES" :key="ty">
          <span class="legend-swatch" :style="{ background: GRAPH_TYPE_FILL[ty] }" /> {{ TYPE_LABELS[ty] }}
        </div>
        <template v-if="mode === 'units'">
          <v-divider vertical class="mx-1" />
          <div v-for="s in ITEM_STATES" :key="s" class="d-flex align-center gap-2">
            <span class="legend-ring" :style="{ borderColor: GRAPH_STATE_BORDER[s] }" /> {{ STATE_LABELS[s] }}
          </div>
        </template>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">
          {{ mode === 'templates' ? $t('graph.clickTemplate') : $t('graph.clickItem') }}
        </span>
      </div>
      <v-divider />
      <div class="graph-stage">
        <HierarchyGraph :data="data" :kind="mode === 'templates' ? 'templates' : 'items'" @node-click="onNodeClick" />
        <v-overlay :model-value="loading" contained class="align-center justify-center" scrim="transparent">
          <v-progress-circular indeterminate color="primary" size="48" />
        </v-overlay>
        <EmptyState
          v-if="!loading && nodeCount === 0"
          class="graph-empty"
          icon="mdi-graph-outline"
          :title="$t('graph.noData')"
          :text="mode === 'templates' ? $t('graph.noTemplatesHint') : $t('graph.noUnitsHint')"
        />
      </div>
    </v-card>
  </v-container>
</template>

<style scoped>
.graph-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 16px;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.legend-swatch {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  display: inline-block;
}
.legend-ring {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 3px solid;
  display: inline-block;
}
.graph-stage {
  position: relative;
}
.graph-empty {
  position: absolute;
  inset: 0;
  background: rgb(var(--v-theme-surface));
}
</style>
