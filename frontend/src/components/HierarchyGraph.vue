<script setup lang="ts">
// A top-down hierarchy drawn with vis-network — of live items or of templates.
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { Network } from 'vis-network'
import { DataSet } from 'vis-data'
import 'vis-network/styles/vis-network.css'
import { useI18n } from 'vue-i18n'
import { useTheme } from 'vuetify'
import { useThemeStore } from '@/stores/theme'
import {
  CARD_TYPE_LABELS,
  GRAPH_STATE_BORDER,
  GRAPH_TYPE_FILL,
  STATE_LABELS,
  TYPE_LABELS,
} from '@/constants'
import type { GraphNode, GraphOut, ItemState, ItemType } from '@/api/types'

const props = withDefaults(
  defineProps<{
    data: GraphOut | null
    kind?: 'items' | 'templates'
    height?: string
    /** Draw this node emphasised (the item whose page this is). */
    focusId?: number | null
  }>(),
  { kind: 'items', height: 'min(76vh, 780px)', focusId: null },
)

const emit = defineEmits<{ 'node-click': [node: GraphNode] }>()

const themeStore = useThemeStore()
const vuetifyTheme = useTheme()
const { t, locale } = useI18n({ useScope: 'global' })
const container = ref<HTMLDivElement | null>(null)
const network = shallowRef<Network | null>(null)

const TYPE_FILL = GRAPH_TYPE_FILL
const STATE_BORDER = GRAPH_STATE_BORDER
const TYPE_SIZE: Record<ItemType, { min: number; max: number }> = {
  setup: { min: 180, max: 240 },
  assembly: { min: 150, max: 210 },
  card: { min: 130, max: 190 },
}

// vis-network's `multi: 'html'` understands <b>; everything else is text.
function esc(v: string): string {
  return v.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function buildNode(n: GraphNode) {
  const size = TYPE_SIZE[n.type]
  const fill = TYPE_FILL[n.type]
  const focused = n.id === props.focusId
  if (props.kind === 'templates') {
    const caption = [
      TYPE_LABELS[n.type],
      n.card_type ? CARD_TYPE_LABELS[n.card_type] : null,
      n.serial,
    ].filter(Boolean).join(' · ')
    return {
      id: n.id,
      label: `<b>${esc(n.label)}</b>\n${esc(caption)}\n${esc(t('graph.units', { n: n.count ?? 0 }))}`,
      color: { background: fill, border: '#ffffff', highlight: { background: fill, border: '#ffd54f' } },
      borderWidth: 2,
      shapeProperties: { borderRadius: 10 },
      margin: { top: 12, right: 16, bottom: 12, left: 16 },
      widthConstraint: size,
      title: caption,
    }
  }
  const state = (n.state ?? 'built') as ItemState
  const faulty = state === 'faulty'
  return {
    id: n.id,
    label: `<b>${esc(n.label)}</b>\n${esc(n.serial ?? '')}\n${esc(STATE_LABELS[state])}`,
    color: {
      background: fill,
      border: focused ? '#ffd54f' : STATE_BORDER[state],
      highlight: { background: fill, border: '#ffd54f' },
      hover: { background: fill, border: STATE_BORDER[state] },
    },
    borderWidth: focused ? 6 : faulty ? 5 : 3,
    shapeProperties: { borderRadius: 10, borderDashes: faulty || state === 'destroyed' ? [6, 4] : false },
    margin: { top: 12, right: 16, bottom: 12, left: 16 },
    widthConstraint: size,
    title: `${TYPE_LABELS[n.type]} · ${STATE_LABELS[state]}`,
  }
}

function render() {
  if (!container.value || !props.data) return
  const nodes = new DataSet(props.data.nodes.map(buildNode))
  const edges = new DataSet(
    props.data.edges.map((e, i) => ({ id: i, from: e.source, to: e.target })),
  )
  const edgeColor = themeStore.isDark ? '#525873' : '#b4b9cc'
  const highlight = vuetifyTheme.current.value.colors.primary
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
      font: {
        multi: 'html',
        color: '#ffffff',
        size: 14,
        face: 'Inter, Roboto, Helvetica, Arial, sans-serif',
        strokeWidth: 4,
        strokeColor: 'rgba(0,0,0,0.5)',
        bold: { size: 18, color: '#ffffff', face: 'Inter, Roboto, Helvetica, Arial, sans-serif' },
      },
    },
    edges: {
      arrows: { to: { enabled: true, scaleFactor: 0.8 } },
      color: { color: edgeColor, highlight, hover: highlight },
      smooth: { enabled: true, type: 'cubicBezier', forceDirection: 'vertical', roundness: 0.6 },
      width: 2,
    },
  }
  const data = { nodes, edges }
  if (network.value) {
    network.value.setData(data as never)
    network.value.setOptions(options as never)
  } else {
    network.value = new Network(container.value, data as never, options as never)
    network.value.on('click', (params: { nodes: (string | number)[] }) => {
      const id = params.nodes[0]
      const node = props.data?.nodes.find((n) => n.id === id)
      if (node) emit('node-click', node)
    })
  }
  network.value.once('afterDrawing', () => network.value?.fit({ animation: false }))
}

watch(() => [props.data, props.focusId, props.kind], render)
watch(() => themeStore.current, render)
watch(locale, render)
onMounted(render)
onBeforeUnmount(() => {
  network.value?.destroy()
  network.value = null
})
</script>

<template>
  <div ref="container" class="graph-canvas" :style="{ height }" dir="ltr" />
</template>

<style scoped>
.graph-canvas {
  min-height: 320px;
  width: 100%;
  background: rgb(var(--v-theme-surface-variant));
  border-radius: 8px;
}
</style>
