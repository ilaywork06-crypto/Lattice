<script setup lang="ts">
import { ref, watch } from 'vue'
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

// ── local, drag-preview copy of the buildings ──────────────────────────────
type Geo = { id: number; x: number; y: number; width: number; height: number; name: string; color: string | null }
const local = ref<Geo[]>([])
function syncLocal() {
  local.value = (props.buildings ?? []).map((b) => ({
    id: b.id, x: b.x, y: b.y, width: b.width, height: b.height, name: b.name, color: b.color,
  }))
}

const DEFAULT_COLOR = '#5b6ef5'
const MIN = 4

function clamp(v: number, lo: number, hi: number) { return Math.min(hi, Math.max(lo, v)) }
function round1(v: number) { return Math.round(v * 10) / 10 }

function toCoords(evt: PointerEvent | MouseEvent): { x: number; y: number } {
  const rect = svgRef.value!.getBoundingClientRect()
  return {
    x: clamp(((evt.clientX - rect.left) / rect.width) * 100, 0, 100),
    y: clamp(((evt.clientY - rect.top) / rect.height) * 100, 0, 100),
  }
}

// ── interaction state ──────────────────────────────────────────────────────
type Handle = 'nw' | 'ne' | 'sw' | 'se'
interface Drag {
  mode: 'draw' | 'move' | 'resize'
  id?: number
  handle?: Handle
  start: { x: number; y: number }
  orig?: { x: number; y: number; width: number; height: number }
  moved: boolean
}
const drag = ref<Drag | null>(null)
const draft = ref<{ x: number; y: number; width: number; height: number } | null>(null)
// After `drag` exists: the immediate run reads it.
watch(() => props.buildings, () => { if (!drag.value) syncLocal() }, { immediate: true, deep: true })

function byId(id: number) { return local.value.find((b) => b.id === id) }

function onDown(evt: PointerEvent) {
  if (!props.editing) return
  const t = evt.target as SVGElement
  const handle = t.dataset.handle as Handle | undefined
  const bAttr = t.dataset.buildingId
  const p = toCoords(evt)
  svgRef.value?.setPointerCapture(evt.pointerId)

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
  const p = toCoords(evt)
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
    b.x = clamp(d.orig.x + (p.x - d.start.x), 0, 100 - b.width)
    b.y = clamp(d.orig.y + (p.y - d.start.y), 0, 100 - b.height)
  } else {
    const o = d.orig
    const right = o.x + o.width
    const bottom = o.y + o.height
    if (d.handle === 'se') {
      b.width = clamp(p.x - o.x, MIN, 100 - o.x)
      b.height = clamp(p.y - o.y, MIN, 100 - o.y)
    } else if (d.handle === 'nw') {
      b.x = clamp(p.x, 0, right - MIN); b.width = right - b.x
      b.y = clamp(p.y, 0, bottom - MIN); b.height = bottom - b.y
    } else if (d.handle === 'ne') {
      b.width = clamp(p.x - o.x, MIN, 100 - o.x)
      b.y = clamp(p.y, 0, bottom - MIN); b.height = bottom - b.y
    } else if (d.handle === 'sw') {
      b.x = clamp(p.x, 0, right - MIN); b.width = right - b.x
      b.height = clamp(p.y - o.y, MIN, 100 - o.y)
    }
  }
}

function onUp(evt: PointerEvent) {
  const d = drag.value
  if (!d) return
  svgRef.value?.releasePointerCapture?.(evt.pointerId)

  if (d.mode === 'draw') {
    const r = draft.value
    if (r && r.width >= 3 && r.height >= 3) {
      emit('building-draw', {
        x: round1(r.x), y: round1(r.y), width: round1(r.width), height: round1(r.height),
      })
    } else {
      // A click (or a too-small smudge) on empty space clears the selection.
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
  if (props.editing || !props.placing || !svgRef.value) return
  const p = toCoords(evt)
  emit('mapclick', { x: round1(p.x), y: round1(p.y) })
}
</script>

<template>
  <!-- dir=ltr: the floor-plan is a spatial coordinate system; it must not
       mirror in RTL locales (only its text labels are localized). -->
  <div class="floorplan-wrap" :class="{ placing, editing }" dir="ltr">
    <svg
      ref="svgRef"
      viewBox="0 0 100 100"
      preserveAspectRatio="xMidYMid meet"
      class="floorplan"
      @click="onMapClick"
      @pointerdown="onDown"
      @pointermove="onMove"
      @pointerup="onUp"
    >
      <!-- building shell -->
      <rect x="1.5" y="1.5" width="97" height="97" rx="3" class="shell" />
      <!-- grid -->
      <g class="grid">
        <line v-for="n in 9" :key="`v${n}`" :x1="n * 10" y1="2" :x2="n * 10" y2="98" />
        <line v-for="n in 9" :key="`h${n}`" x1="2" :y1="n * 10" x2="98" :y2="n * 10" />
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
            rx="1.5"
            class="building-rect"
            :fill="b.color || DEFAULT_COLOR"
            :stroke="b.color || DEFAULT_COLOR"
          />
          <text :x="b.x + 2" :y="b.y + 4.4" class="building-label">{{ b.name }}</text>
          <!-- resize handles (only for the selected building in edit mode) -->
          <template v-if="editing && b.id === selectedBuildingId">
            <rect
              v-for="hp in handlePos(b)"
              :key="hp.h"
              :data-handle="hp.h"
              :x="hp.x - 0.9"
              :y="hp.y - 0.9"
              width="1.8"
              height="1.8"
              class="handle"
              :class="`handle-${hp.h}`"
            />
          </template>
        </g>
      </g>

      <!-- draft rectangle while drawing a new building -->
      <rect
        v-if="draft"
        :x="draft.x"
        :y="draft.y"
        :width="draft.width"
        :height="draft.height"
        rx="1.5"
        class="draft-rect"
      />

      <!-- location markers -->
      <g class="markers" :class="{ dimmed: editing }">
        <g
          v-for="loc in locations"
          :key="loc.id"
          class="marker"
          :class="{ selected: loc.id === selectedId }"
          :transform="`translate(${loc.x}, ${loc.y})`"
          @click.stop="!editing && emit('select', loc.id)"
        >
          <circle
            v-if="loc.id === selectedId"
            r="4.4"
            :fill="markerColor(loc)"
            opacity="0.25"
            class="pulse"
          />
          <circle
            v-if="loc.is_desiccator"
            r="3.3"
            fill="none"
            stroke="#26c6da"
            stroke-width="0.5"
            stroke-dasharray="0.8 0.5"
            class="desiccator-ring"
          />
          <circle r="2.4" :fill="markerColor(loc)" stroke="#ffffff" stroke-width="0.5" />
          <text v-if="loc.item_count" y="0.9" class="count">{{ loc.item_count }}</text>
          <text y="6.2" class="marker-label">{{ loc.name }}</text>
        </g>
      </g>
    </svg>

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
  display: block;
  border-radius: 12px;
  background: rgb(var(--v-theme-surface-variant));
  touch-action: none;
}
.placing .floorplan {
  cursor: crosshair;
  outline: 2px dashed rgb(var(--v-theme-primary));
}
.editing .floorplan {
  cursor: crosshair;
  outline: 2px dashed rgb(var(--v-theme-primary));
}
.shell {
  fill: rgb(var(--v-theme-surface));
  stroke: rgba(128, 128, 128, 0.35);
  stroke-width: 0.4;
}
.grid line {
  stroke: rgba(128, 128, 128, 0.14);
  stroke-width: 0.25;
}
.building-rect {
  fill-opacity: 0.12;
  stroke-opacity: 0.55;
  stroke-width: 0.3;
  pointer-events: none;
}
.buildings.interactive .building-rect {
  pointer-events: auto;
  cursor: move;
}
.buildings .selected .building-rect {
  fill-opacity: 0.2;
  stroke-opacity: 0.9;
  stroke-width: 0.6;
}
.building-label {
  font-size: 2.4px;
  fill: rgb(var(--v-theme-on-surface));
  opacity: 0.72;
  font-weight: 700;
  pointer-events: none;
}
.handle {
  fill: #ffffff;
  stroke: #5b6ef5;
  stroke-width: 0.4;
}
.handle-nw, .handle-se { cursor: nwse-resize; }
.handle-ne, .handle-sw { cursor: nesw-resize; }
.draft-rect {
  fill: rgba(91, 110, 245, 0.18);
  stroke: #5b6ef5;
  stroke-width: 0.4;
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
  font-size: 2.1px;
  fill: #ffffff;
  text-anchor: middle;
  font-weight: 700;
  pointer-events: none;
}
.marker-label {
  font-size: 2.2px;
  fill: rgb(var(--v-theme-on-surface));
  text-anchor: middle;
  font-weight: 600;
  pointer-events: none;
}
.marker circle {
  transition: r 0.15s ease;
}
.marker:hover circle {
  r: 2.9;
}
.marker:hover .desiccator-ring {
  r: 3.8;
}
.pulse {
  animation: pulse 1.8s ease-in-out infinite;
  transform-origin: center;
}
@keyframes pulse {
  0%, 100% { opacity: 0.12; }
  50% { opacity: 0.32; }
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
