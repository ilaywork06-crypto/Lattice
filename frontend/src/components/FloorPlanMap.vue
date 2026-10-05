<script setup lang="ts">
// The floor-plan: a 100 × 100 coordinate plane (every location and building
// is placed in 0..100 on both axes), with zoom, pan and adjustable label size.
//
// * Zoom: mouse wheel (around the cursor) or the +/− buttons; reset fits the
//   whole 100 × 100 plan. The grid gets finer as you zoom (10 → 5 → 1).
// * Pan: drag empty space (or, while editing buildings, drag with the middle
//   mouse button / hold Shift).
// * Text size: A−/A+ scale every label; the choice is remembered.
// Labels and markers keep a constant on-screen size whatever the zoom.
import { computed, onMounted, ref, watch } from 'vue'
import type { LocationOut, MapBuilding } from '@/api/types'

const props = defineProps<{
  locations: LocationOut[]
  selectedId: number | null
  placing?: boolean
  buildings?: MapBuilding[]
  editing?: boolean
  selectedBuildingId?: number | null
}>()

const emit = defineEmits<{
  select: [id: number]
  mapclick: [coords: { x: number; y: number }]
  'select-building': [id: number]
  'deselect-building': []
  'building-draw': [rect: { x: number; y: number; width: number; height: number }]
  'building-change': [
    geo: { id: number; x: number; y: number; width: number; height: number },
  ]
}>()

const svgRef = ref<SVGSVGElement | null>(null)

// ── view (zoom + pan) ───────────────────────────────────────────────────────
const SIZE = 100
const PAD = 6 // room for the axis labels around the plan at zoom 1
const MIN_ZOOM = 1
const MAX_ZOOM = 12
const zoom = ref(1)
const center = ref({ x: SIZE / 2, y: SIZE / 2 })

const viewSize = computed(() => (SIZE + PAD * 2) / zoom.value)
const view = computed(() => {
  const s = viewSize.value
  const lo = -PAD
  const hi = SIZE + PAD - s
  return {
    x: clamp(center.value.x - s / 2, lo, Math.max(lo, hi)),
    y: clamp(center.value.y - s / 2, lo, Math.max(lo, hi)),
    s,
  }
})
const viewBox = computed(() => `${view.value.x} ${view.value.y} ${view.value.s} ${view.value.s}`)
/** One screen-constant unit: sizes multiplied by this stay the same on screen. */
const u = computed(() => 1 / zoom.value)

function setZoom(next: number, anchor?: { x: number; y: number }) {
  const z = clamp(next, MIN_ZOOM, MAX_ZOOM)
  if (anchor) {
    // keep the point under the cursor where it is
    const ratio = zoom.value / z
    center.value = {
      x: anchor.x - (anchor.x - center.value.x) * ratio,
      y: anchor.y - (anchor.y - center.value.y) * ratio,
    }
  }
  zoom.value = z
  if (z === MIN_ZOOM) center.value = { x: SIZE / 2, y: SIZE / 2 }
}
function zoomIn() {
  setZoom(zoom.value * 1.5)
}
function zoomOut() {
  setZoom(zoom.value / 1.5)
}
function resetView() {
  zoom.value = 1
  center.value = { x: SIZE / 2, y: SIZE / 2 }
}

function onWheel(evt: WheelEvent) {
  evt.preventDefault()
  const p = toPlan(evt, false)
  setZoom(zoom.value * (evt.deltaY < 0 ? 1.2 : 1 / 1.2), p)
}

// ── label size (remembered) ─────────────────────────────────────────────────
const FONT_KEY = 'lattice.map.fontScale'
const fontScale = ref(1)
onMounted(() => {
  try {
    const v = Number(localStorage.getItem(FONT_KEY))
    if (v >= 0.6 && v <= 2.5) fontScale.value = v
  } catch {
    // storage unavailable — default size
  }
})
watch(fontScale, (v) => {
  try {
    localStorage.setItem(FONT_KEY, String(v))
  } catch {
    // ignore
  }
})
function fontBigger() {
  fontScale.value = Math.min(2.5, Math.round((fontScale.value + 0.2) * 10) / 10)
}
function fontSmaller() {
  fontScale.value = Math.max(0.6, Math.round((fontScale.value - 0.2) * 10) / 10)
}
const fs = (base: number) => base * fontScale.value * u.value

// ── grid ────────────────────────────────────────────────────────────────────
const gridStep = computed(() => (zoom.value >= 5 ? 1 : zoom.value >= 2 ? 5 : 10))
const gridLines = computed(() => {
  const step = gridStep.value
  const out: number[] = []
  for (let v = step; v < SIZE; v += step) out.push(v)
  return out
})
const labelStep = computed(() => (zoom.value >= 6 ? 1 : zoom.value >= 3 ? 5 : 10))
const axisLabels = computed(() => {
  const out: number[] = []
  for (let v = 0; v <= SIZE; v += labelStep.value) out.push(v)
  return out.filter(
    (v) => v >= view.value.x - 1 && v <= view.value.x + view.value.s + 1,
  )
})
const axisLabelsY = computed(() => {
  const out: number[] = []
  for (let v = 0; v <= SIZE; v += labelStep.value) out.push(v)
  return out.filter((v) => v >= view.value.y - 1 && v <= view.value.y + view.value.s + 1)
})
// Axis labels hug the visible edge of the plan.
const axisTop = computed(() => Math.max(view.value.y, -PAD) + 2.6 * fontScale.value * u.value)
const axisLeft = computed(() => Math.max(view.value.x, -PAD) + 0.6 * u.value)

const DEFAULT_COLOR = '#5b6ef5'
const MIN = 2

function clamp(v: number, lo: number, hi: number) { return Math.min(hi, Math.max(lo, v)) }
function round1(v: number) { return Math.round(v * 10) / 10 }

/** Client → plan coordinates, exact at any zoom (via the SVG's own matrix). */
function toPlan(evt: { clientX: number; clientY: number }, clampToPlan = true): { x: number; y: number } {
  const svg = svgRef.value!
  const pt = svg.createSVGPoint()
  pt.x = evt.clientX
  pt.y = evt.clientY
  const ctm = svg.getScreenCTM()
  const p = ctm ? pt.matrixTransform(ctm.inverse()) : { x: 0, y: 0 }
  return clampToPlan ? { x: clamp(p.x, 0, SIZE), y: clamp(p.y, 0, SIZE) } : { x: p.x, y: p.y }
}

// ── interaction state ──────────────────────────────────────────────────────
type Handle = 'nw' | 'ne' | 'sw' | 'se'
interface Drag {
  mode: 'draw' | 'move' | 'resize' | 'pan'
  id?: number
  handle?: Handle
  start: { x: number; y: number }
  client?: { x: number; y: number }
  orig?: { x: number; y: number; width: number; height: number }
  origCenter?: { x: number; y: number }
  moved: boolean
}
const drag = ref<Drag | null>(null)
const draft = ref<{ x: number; y: number; width: number; height: number } | null>(null)
const panning = computed(() => drag.value?.mode === 'pan')

// ── local, drag-preview copy of the buildings ──────────────────────────────
type Geo = { id: number; x: number; y: number; width: number; height: number; name: string; color: string | null }
const local = ref<Geo[]>([])
function syncLocal() {
  local.value = (props.buildings ?? []).map((b) => ({
    id: b.id, x: b.x, y: b.y, width: b.width, height: b.height, name: b.name, color: b.color,
  }))
}
watch(() => props.buildings, () => { if (!drag.value) syncLocal() }, { immediate: true, deep: true })

function byId(id: number) { return local.value.find((b) => b.id === id) }

function startPan(evt: PointerEvent) {
  drag.value = {
    mode: 'pan',
    start: toPlan(evt, false),
    client: { x: evt.clientX, y: evt.clientY },
    origCenter: { ...center.value },
    moved: false,
  }
}

function onDown(evt: PointerEvent) {
  const t = evt.target as SVGElement
  const onMarker = !!t.closest?.('.marker')
  svgRef.value?.setPointerCapture(evt.pointerId)

  if (!props.editing) {
    // Drag empty space to pan (a plain click still selects / places).
    if (!onMarker && zoom.value > 1) startPan(evt)
    return
  }
  if (evt.button === 1 || evt.shiftKey) {
    startPan(evt)
    return
  }
  const handle = t.dataset.handle as Handle | undefined
  const bAttr = t.dataset.buildingId
  const p = toPlan(evt)

  if (handle && props.selectedBuildingId != null) {
    const b = byId(props.selectedBuildingId)
    if (!b) return
    drag.value = { mode: 'resize', id: b.id, handle, start: p, orig: { ...b }, moved: false }
  } else if (bAttr) {
    const id = Number(bAttr)
    emit('select-building', id)
    const b = byId(id)
    if (!b) return
    drag.value = { mode: 'move', id, start: p, orig: { ...b }, moved: false }
  } else {
    drag.value = { mode: 'draw', start: p, moved: false }
    draft.value = { x: p.x, y: p.y, width: 0, height: 0 }
  }
}

function onMove(evt: PointerEvent) {
  const d = drag.value
  if (!d) return

  if (d.mode === 'pan') {
    const rect = svgRef.value!.getBoundingClientRect()
    const scale = view.value.s / Math.min(rect.width, rect.height)
    const dx = (evt.clientX - d.client!.x) * scale
    const dy = (evt.clientY - d.client!.y) * scale
    if (Math.abs(dx) + Math.abs(dy) > 0.3) d.moved = true
    center.value = { x: d.origCenter!.x - dx, y: d.origCenter!.y - dy }
    return
  }

  const p = toPlan(evt)
  d.moved = true
  if (d.mode === 'draw') {
    draft.value = {
      x: Math.min(d.start.x, p.x),
      y: Math.min(d.start.y, p.y),
      width: Math.abs(p.x - d.start.x),
      height: Math.abs(p.y - d.start.y),
    }
    return
  }
  const b = byId(d.id!)
  if (!b || !d.orig) return

  if (d.mode === 'move') {
    b.x = clamp(d.orig.x + (p.x - d.start.x), 0, SIZE - b.width)
    b.y = clamp(d.orig.y + (p.y - d.start.y), 0, SIZE - b.height)
  } else {
    const o = d.orig
    const right = o.x + o.width
    const bottom = o.y + o.height
    if (d.handle === 'se') {
      b.width = clamp(p.x - o.x, MIN, SIZE - o.x)
      b.height = clamp(p.y - o.y, MIN, SIZE - o.y)
    } else if (d.handle === 'nw') {
      b.x = clamp(p.x, 0, right - MIN); b.width = right - b.x
      b.y = clamp(p.y, 0, bottom - MIN); b.height = bottom - b.y
    } else if (d.handle === 'ne') {
      b.width = clamp(p.x - o.x, MIN, SIZE - o.x)
      b.y = clamp(p.y, 0, bottom - MIN); b.height = bottom - b.y
    } else if (d.handle === 'sw') {
      b.x = clamp(p.x, 0, right - MIN); b.width = right - b.x
      b.height = clamp(p.y - o.y, MIN, SIZE - o.y)
    }
  }
}

let suppressClick = false

function onUp(evt: PointerEvent) {
  const d = drag.value
  if (!d) return
  svgRef.value?.releasePointerCapture?.(evt.pointerId)

  if (d.mode === 'pan') {
    suppressClick = d.moved
  } else if (d.mode === 'draw') {
    const r = draft.value
    if (r && r.width >= 1 && r.height >= 1) {
      emit('building-draw', {
        x: round1(r.x), y: round1(r.y), width: round1(r.width), height: round1(r.height),
      })
    } else {
      emit('deselect-building')
    }
    draft.value = null
  } else if (d.moved) {
    const b = byId(d.id!)
    if (b) {
      emit('building-change', {
        id: b.id, x: round1(b.x), y: round1(b.y), width: round1(b.width), height: round1(b.height),
      })
    }
  }
  drag.value = null
}

function handlePos(b: Geo): { h: Handle; x: number; y: number }[] {
  return [
    { h: 'nw', x: b.x, y: b.y },
    { h: 'ne', x: b.x + b.width, y: b.y },
    { h: 'sw', x: b.x, y: b.y + b.height },
    { h: 'se', x: b.x + b.width, y: b.y + b.height },
  ]
}

function markerColor(loc: LocationOut): string {
  if (loc.id === props.selectedId) return '#5b6ef5'
  if (loc.item_count === 0) return '#9aa0b4'
  if (loc.item_count >= 10) return '#e5484d'
  if (loc.item_count >= 4) return '#e6a532'
  return '#2e9e5b'
}

function onMapClick(evt: MouseEvent) {
  if (suppressClick) {
    suppressClick = false
    return
  }
  if (props.editing || !props.placing || !svgRef.value) return
  const p = toPlan(evt)
  emit('mapclick', { x: round1(p.x), y: round1(p.y) })
}

function onMarkerClick(id: number) {
  if (suppressClick) {
    suppressClick = false
    return
  }
  if (!props.editing) emit('select', id)
}
</script>

<template>
  <!-- dir=ltr: the floor-plan is a spatial coordinate system; it must not
       mirror in RTL locales (only its text labels are localized). -->
  <div class="floorplan-wrap" :class="{ placing, editing, panning, zoomed: zoom > 1 }" dir="ltr">
    <svg
      ref="svgRef"
      :viewBox="viewBox"
      preserveAspectRatio="xMidYMid meet"
      class="floorplan"
      @click="onMapClick"
      @wheel="onWheel"
      @pointerdown="onDown"
      @pointermove="onMove"
      @pointerup="onUp"
    >
      <!-- the 100 × 100 plan -->
      <rect x="0" y="0" :width="SIZE" :height="SIZE" class="shell" :stroke-width="0.4 * u" />
      <g class="grid">
        <line
          v-for="n in gridLines"
          :key="`v${n}`"
          :x1="n" y1="0" :x2="n" :y2="SIZE"
          :class="{ major: n % 10 === 0 }"
          :stroke-width="(n % 10 === 0 ? 0.35 : 0.18) * u"
        />
        <line
          v-for="n in gridLines"
          :key="`h${n}`"
          x1="0" :y1="n" :x2="SIZE" :y2="n"
          :class="{ major: n % 10 === 0 }"
          :stroke-width="(n % 10 === 0 ? 0.35 : 0.18) * u"
        />
      </g>
      <!-- axis labels -->
      <g class="axis">
        <text
          v-for="v in axisLabels"
          :key="`ax${v}`"
          :x="v"
          :y="axisTop"
          text-anchor="middle"
          :font-size="fs(2)"
        >{{ v }}</text>
        <text
          v-for="v in axisLabelsY"
          :key="`ay${v}`"
          :x="axisLeft"
          :y="v + fs(0.7)"
          text-anchor="start"
          :font-size="fs(2)"
        >{{ v }}</text>
      </g>

      <!-- editable buildings -->
      <g class="buildings" :class="{ interactive: editing }">
        <g v-for="b in local" :key="b.id" :class="{ selected: b.id === selectedBuildingId }">
          <rect
            :data-building-id="b.id"
            :x="b.x"
            :y="b.y"
            :width="b.width"
            :height="b.height"
            :rx="1.2 * u"
            class="building-rect"
            :fill="b.color || DEFAULT_COLOR"
            :stroke="b.color || DEFAULT_COLOR"
            :stroke-width="(b.id === selectedBuildingId ? 0.6 : 0.3) * u"
          />
          <text :x="b.x + 1.2 * u" :y="b.y + fs(3)" class="building-label" :font-size="fs(2.6)">{{ b.name }}</text>
          <template v-if="editing && b.id === selectedBuildingId">
            <rect
              v-for="hp in handlePos(b)"
              :key="hp.h"
              :data-handle="hp.h"
              :x="hp.x - 0.9 * u"
              :y="hp.y - 0.9 * u"
              :width="1.8 * u"
              :height="1.8 * u"
              class="handle"
              :class="`handle-${hp.h}`"
              :stroke-width="0.4 * u"
            />
          </template>
        </g>
      </g>

      <rect
        v-if="draft"
        :x="draft.x"
        :y="draft.y"
        :width="draft.width"
        :height="draft.height"
        class="draft-rect"
        :stroke-width="0.4 * u"
      />

      <!-- location markers -->
      <g class="markers" :class="{ dimmed: editing }">
        <g
          v-for="loc in locations"
          :key="loc.id"
          class="marker"
          :class="{ selected: loc.id === selectedId }"
          :transform="`translate(${loc.x}, ${loc.y})`"
          @click.stop="onMarkerClick(loc.id)"
        >
          <circle v-if="loc.id === selectedId" :r="4.4 * u" :fill="markerColor(loc)" opacity="0.25" class="pulse" />
          <circle
            v-if="loc.is_desiccator"
            :r="3.3 * u"
            fill="none"
            stroke="#26c6da"
            :stroke-width="0.5 * u"
            :stroke-dasharray="`${0.8 * u} ${0.5 * u}`"
          />
          <circle :r="2.4 * u" :fill="markerColor(loc)" stroke="#ffffff" :stroke-width="0.5 * u" />
          <text v-if="loc.item_count" :y="fs(0.75)" class="count" :font-size="fs(2.1)">{{ loc.item_count }}</text>
          <text :y="fs(2.2) + 3.6 * u" class="marker-label" :font-size="fs(2.2)">{{ loc.name }}</text>
        </g>
      </g>
    </svg>

    <!-- zoom & text controls -->
    <div class="map-controls" @pointerdown.stop>
      <v-btn-group density="compact" variant="flat" rounded="lg" class="elevation-2">
        <v-btn icon="mdi-plus" size="small" :title="$t('map.zoomIn')" :disabled="zoom >= MAX_ZOOM" @click="zoomIn" />
        <v-btn icon="mdi-minus" size="small" :title="$t('map.zoomOut')" :disabled="zoom <= MIN_ZOOM" @click="zoomOut" />
        <v-btn icon="mdi-fit-to-screen-outline" size="small" :title="$t('map.resetView')" @click="resetView" />
      </v-btn-group>
      <v-btn-group density="compact" variant="flat" rounded="lg" class="elevation-2">
        <v-btn size="small" :title="$t('map.textSmaller')" :disabled="fontScale <= 0.6" @click="fontSmaller">A−</v-btn>
        <v-btn size="small" :title="$t('map.textBigger')" :disabled="fontScale >= 2.5" @click="fontBigger">A+</v-btn>
      </v-btn-group>
      <span class="zoom-readout">{{ Math.round(zoom * 100) }}%</span>
    </div>

    <div v-if="placing && !editing" class="map-hint">
      <v-icon icon="mdi-cursor-default-click" size="16" /> {{ $t('map.placingHint') }}
    </div>
    <div v-else-if="editing" class="map-hint edit">
      <v-icon icon="mdi-pencil-ruler" size="16" /> {{ $t('map.editHint') }}
    </div>
  </div>
</template>

<style scoped>
.floorplan-wrap {
  position: relative;
  width: 100%;
}
.floorplan {
  width: 100%;
  aspect-ratio: 1 / 1;
  max-height: 82vh;
  display: block;
  border-radius: 12px;
  background: rgb(var(--v-theme-surface-variant));
  touch-action: none;
  user-select: none;
}
.zoomed .floorplan {
  cursor: grab;
}
.panning .floorplan {
  cursor: grabbing;
}
.placing .floorplan,
.editing .floorplan {
  cursor: crosshair;
  outline: 2px dashed rgb(var(--v-theme-primary));
}
/* Vuetify's cards set letter-spacing in em, which is inherited as an absolute
   length — on text sized in plan units it spread every label apart. */
.floorplan text {
  letter-spacing: normal;
}
.shell {
  fill: rgb(var(--v-theme-surface));
  stroke: rgba(128, 128, 128, 0.45);
}
.grid line {
  stroke: rgba(128, 128, 128, 0.12);
}
.grid line.major {
  stroke: rgba(128, 128, 128, 0.25);
}
.axis text {
  fill: rgb(var(--v-theme-on-surface));
  opacity: 0.45;
  pointer-events: none;
}
.building-rect {
  fill-opacity: 0.12;
  stroke-opacity: 0.55;
  pointer-events: none;
}
.buildings.interactive .building-rect {
  pointer-events: auto;
  cursor: move;
}
.buildings .selected .building-rect {
  fill-opacity: 0.2;
  stroke-opacity: 0.9;
}
.building-label {
  fill: rgb(var(--v-theme-on-surface));
  opacity: 0.72;
  font-weight: 700;
  pointer-events: none;
}
.handle {
  fill: #ffffff;
  stroke: #5b6ef5;
}
.handle-nw, .handle-se { cursor: nwse-resize; }
.handle-ne, .handle-sw { cursor: nesw-resize; }
.draft-rect {
  fill: rgba(91, 110, 245, 0.18);
  stroke: #5b6ef5;
  stroke-dasharray: 1.4 1;
  pointer-events: none;
}
.markers.dimmed {
  opacity: 0.45;
  pointer-events: none;
}
.marker {
  cursor: pointer;
}
.marker .count {
  fill: #ffffff;
  text-anchor: middle;
  font-weight: 700;
  pointer-events: none;
}
.marker-label {
  fill: rgb(var(--v-theme-on-surface));
  text-anchor: middle;
  font-weight: 600;
  pointer-events: none;
  paint-order: stroke;
  stroke: rgb(var(--v-theme-surface));
  stroke-width: 0.35px;
}
.pulse {
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.12; }
  50% { opacity: 0.32; }
}
.map-controls {
  position: absolute;
  bottom: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.zoom-readout {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 8px;
  background: rgba(var(--v-theme-surface), 0.85);
}
.map-hint {
  position: absolute;
  top: 10px;
  left: 10px;
  background: rgb(var(--v-theme-primary));
  color: #fff;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.map-hint.edit {
  background: rgb(var(--v-theme-secondary, 124 77 255));
}
</style>
