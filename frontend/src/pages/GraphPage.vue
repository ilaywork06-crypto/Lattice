<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Network } from 'vis-network'
import { DataSet } from 'vis-data'
import 'vis-network/styles/vis-network.css'
import { graphApi, itemsApi } from '@/api/services'
import { useThemeStore } from '@/stores/theme'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { STATE_LABELS, TYPE_LABELS } from '@/constants'
import { useI18n } from 'vue-i18n'
import type { GraphNode, ItemState, ItemType } from '@/api/types'

const router = useRouter()
const themeStore = useThemeStore()
const ui = useUiStore()
const { t, locale } = useI18n({ useScope: 'global' })

const container = ref<HTMLDivElement | null>(null)
const network = shallowRef<Network | null>(null)
const loading = ref(false)
const nodeCount = ref(0)

const rootId = ref<number | null>(null)
const rootOptions = ref<{ title: string; value: number | null }[]>([{ title: t('graph.entireHierarchy'), value: null }])

const TYPE_FILL: Record<ItemType, string> = {
  setup: '#6d4bb6',
  assembly: '#1f9488',
  card: '#2f7fd4',
}
const STATE_BORDER: Record<ItemState, string> = {
  working: '#2e9e5b',
  faulty: '#e5484d',
  built: '#2f80ed',
  production: '#e6a532',
  used: '#8a8f9a',
}
// Each type gets a slightly different footprint so the three tiers read at a
// glance even before you read the label.
const TYPE_SIZE: Record<ItemType, { min: number; max: number }> = {
  setup: { min: 180, max: 240 },
  assembly: { min: 150, max: 210 },
  card: { min: 130, max: 190 },
}

function buildNode(n: GraphNode) {
  const faulty = n.state === 'faulty'
  const size = TYPE_SIZE[n.type]
  return {
    id: n.id,
    // Bold name on line 1, a clear "type · state" caption on line 2.
    label: `*${n.label}*\n${TYPE_LABELS[n.type]} · ${STATE_LABELS[n.state]}`,
    shape: 'box',
    color: {
      background: TYPE_FILL[n.type],
      border: STATE_BORDER[n.state],
      highlight: { background: TYPE_FILL[n.type], border: STATE_BORDER[n.state] },
      hover: { background: TYPE_FILL[n.type], border: STATE_BORDER[n.state] },
    },
    borderWidth: faulty ? 5 : 3,
    shapeProperties: { borderRadius: 10, borderDashes: faulty ? [6, 4] : false },
    margin: { top: 12, right: 16, bottom: 12, left: 16 },
    widthConstraint: size,
    title: `${TYPE_LABELS[n.type]} · ${STATE_LABELS[n.state]}`,
  }
}

async function loadRoots() {
  try {
    const setups = await itemsApi.list({ type: 'setup', limit: 500 })
    rootOptions.value = [
      { title: t('graph.entireHierarchy'), value: null },
      ...setups.map((s) => ({ title: s.name, value: s.id })),
    ]
  } catch {
    // non-fatal
  }
}

async function loadGraph() {
  loading.value = true
  try {
    const data = await graphApi.get(rootId.value ?? undefined)
    nodeCount.value = data.nodes.length
    const nodes = new DataSet(data.nodes.map(buildNode))
    const edges = new DataSet(
      data.edges.map((e, i) => ({ id: i, from: e.source, to: e.target })),
    )
    render({ nodes, edges })
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

function render(data: { nodes: DataSet<any>; edges: DataSet<any> }) {
  if (!container.value) return
  const edgeColor = themeStore.isDark ? '#525873' : '#b4b9cc'
  const options = {
    autoResize: true,
    layout: {
      hierarchical: {
        enabled: true,
        direction: 'UD',
        sortMethod: 'directed',
        shakeTowards: 'roots',
        levelSeparation: 170,
        nodeSpacing: 210,
        treeSpacing: 260,
        blockShifting: true,
        edgeMinimization: true,
        parentCentralization: true,
      },
    },
    physics: { enabled: false },
    interaction: {
      hover: true,
      tooltipDelay: 120,
      navigationButtons: true,
      keyboard: false,
      zoomView: true,
      dragView: true,
    },
    nodes: {
      shape: 'box',
      // Larger, high-contrast label with a dark halo so it stays crisp on any
      // node colour. Bold name (multi) + lighter caption line.
      font: {
        multi: true,
        color: '#ffffff',
        size: 15,
        face: 'Inter, Roboto, Helvetica, Arial, sans-serif',
        strokeWidth: 4,
        strokeColor: 'rgba(0,0,0,0.55)',
        bold: { size: 19, color: '#ffffff', face: 'Inter, Roboto, Helvetica, Arial, sans-serif' },
      },
    },
    edges: {
      arrows: { to: { enabled: true, scaleFactor: 0.8 } },
      color: { color: edgeColor, highlight: '#5b6ef5', hover: '#5b6ef5' },
      smooth: { enabled: true, type: 'cubicBezier', forceDirection: 'vertical', roundness: 0.6 },
      width: 2,
      hoverWidth: 1,
      selectionWidth: 2,
    },
  }
  if (network.value) {
    network.value.setData(data as any)
    network.value.setOptions(options as any)
  } else {
    network.value = new Network(container.value, data as any, options as any)
    network.value.on('click', (params: { nodes: (string | number)[] }) => {
      if (params.nodes.length) {
        router.push(`/items/${params.nodes[0]}`)
      }
    })
  }
  network.value.once('afterDrawing', () => network.value?.fit({ animation: false }))
}

watch(rootId, loadGraph)
watch(
  () => themeStore.isDark,
  () => loadGraph(),
)
// Re-render so node captions (type · state) follow the language switch.
watch(locale, () => {
  void loadRoots()
  void loadGraph()
})

onMounted(async () => {
  await loadRoots()
  await loadGraph()
})
onBeforeUnmount(() => {
  network.value?.destroy()
  network.value = null
})
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader
      :title="$t('nav.graph')"
      :subtitle="$t('graph.subtitle')"
      icon="mdi-graph-outline"
    >
      <template #actions>
        <v-select
          v-model="rootId"
          :label="$t('graph.root')"
          hide-details
          density="comfortable"
          style="min-width: 220px"
          :items="rootOptions"
        />
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="loadGraph" />
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-card-text class="pa-0">
        <div class="graph-toolbar">
          <div class="d-flex flex-wrap align-center gap-4">
            <div class="d-flex align-center gap-2">
              <span class="legend-swatch" style="background: #7e57c2" /> {{ $t('enums.type.setup') }}
            </div>
            <div class="d-flex align-center gap-2">
              <span class="legend-swatch" style="background: #26a69a" /> {{ $t('enums.type.assembly') }}
            </div>
            <div class="d-flex align-center gap-2">
              <span class="legend-swatch" style="background: #42a5f5" /> {{ $t('enums.type.card') }}
            </div>
            <v-divider vertical class="mx-1" />
            <div
              v-for="s in (['working', 'built', 'production', 'used', 'faulty'] as ItemState[])"
              :key="s"
              class="d-flex align-center gap-2"
            >
              <span
                class="legend-ring"
                :style="{ borderColor: STATE_BORDER[s] }"
              />
              {{ STATE_LABELS[s] }}
            </div>
          </div>
          <v-chip size="small" variant="tonal" color="primary">{{ $t('graph.nodes', { n: nodeCount }) }}</v-chip>
        </div>
        <v-divider />
        <div class="graph-stage">
          <div ref="container" class="graph-canvas" dir="ltr" />
          <v-overlay
            :model-value="loading"
            contained
            class="align-center justify-center"
            scrim="transparent"
          >
            <v-progress-circular indeterminate color="primary" size="48" />
          </v-overlay>
          <EmptyState
            v-if="!loading && nodeCount === 0"
            class="graph-empty"
            icon="mdi-graph-outline"
            :title="$t('graph.noData')"
            :text="$t('graph.noDataHint')"
          />
        </div>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<style scoped>
.graph-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 16px;
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
.graph-canvas {
  height: min(76vh, 780px);
  min-height: 520px;
  width: 100%;
  background: rgb(var(--v-theme-surface-variant));
}
.graph-empty {
  position: absolute;
  inset: 0;
  background: rgb(var(--v-theme-surface));
}
</style>
