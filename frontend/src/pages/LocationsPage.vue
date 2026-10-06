<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { itemsApi, locationsApi, mapApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import FloorPlanMap from '@/components/FloorPlanMap.vue'
import TypeIcon from '@/components/TypeIcon.vue'
import StateChip from '@/components/StateChip.vue'
import ConfirmDialog from '@/components/dialogs/ConfirmDialog.vue'
import type { ItemListOut, LocationOut, MapBuilding } from '@/api/types'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const { t } = useI18n({ useScope: 'global' })

const locations = ref<LocationOut[]>([])
const buildings = ref<MapBuilding[]>([])
const loading = ref(false)
const selectedId = ref<number | null>(null)
const selected = ref<LocationOut | null>(null)
const items = ref<ItemListOut[]>([])
const itemsLoading = ref(false)

const headers = computed(() => [
  { title: t('fields.name'), key: 'name' },
  { title: t('loc.colBuilding'), key: 'building' },
  { title: t('loc.colRoom'), key: 'room' },
  { title: t('loc.colItems'), key: 'item_count', align: 'center', width: 90 },
  { title: t('fieldInput.desiccator'), key: 'is_desiccator', align: 'center', width: 110 },
  { title: 'X', key: 'x', width: 70 },
  { title: 'Y', key: 'y', width: 70 },
  { title: '', key: 'actions', sortable: false, align: 'end', width: 120 },
])

async function load() {
  loading.value = true
  try {
    locations.value = await locationsApi.list()
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

async function loadBuildings() {
  try {
    buildings.value = await mapApi.buildings()
  } catch (e) {
    ui.error(e)
  }
}

async function selectLocation(id: number) {
  selectedId.value = id
  selected.value = locations.value.find((l) => l.id === id) ?? null
  itemsLoading.value = true
  try {
    items.value = await itemsApi.list({ location_id: id, limit: 500 })
  } catch (e) {
    ui.error(e)
  } finally {
    itemsLoading.value = false
  }
}

// ---- Create / edit --------------------------------------------------------
const dialog = ref(false)
const editing = ref<LocationOut | null>(null)
const saving = ref(false)
const form = reactive<{
  name: string
  building: string
  room: string
  x: number
  y: number
  notes: string
}>({ name: '', building: '', room: '', x: 50, y: 50, notes: '' })

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', building: '', room: '', x: 50, y: 50, notes: '' })
  mapEdit.value = false // placing a marker and reshaping the plan are exclusive modes
  picking.value = false
  dialog.value = true
}
function openEdit(loc: LocationOut) {
  editing.value = loc
  mapEdit.value = false
  picking.value = false
  Object.assign(form, {
    name: loc.name,
    building: loc.building ?? '',
    room: loc.room ?? '',
    x: loc.x,
    y: loc.y,
    notes: loc.notes ?? '',
  })
  dialog.value = true
}
// ---- Picking coordinates off the plan -------------------------------------
// The dialog is a modal: its scrim covers the viewport, so a click aimed at the
// floor-plan would hit the scrim and merely dismiss the dialog. So picking is a
// step of its own — the dialog steps aside, the plan takes one click, and the
// dialog comes back with the coordinates filled in. Form state survives because
// nothing resets it on close.
const picking = ref(false)
const planAnchor = ref<HTMLElement | null>(null)

function startPicking() {
  picking.value = true
  dialog.value = false
  // The dialog is often opened from the table far below; bring the plan into view.
  nextTick(() => planAnchor.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
}

function cancelPicking() {
  picking.value = false
  dialog.value = true
}

function onMapPlace(coords: { x: number; y: number }) {
  if (!picking.value) return
  form.x = coords.x
  form.y = coords.y
  picking.value = false
  dialog.value = true
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && picking.value) cancelPicking()
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

async function save() {
  if (!form.name.trim()) {
    ui.warning(t('loc.nameRequired'))
    return
  }
  saving.value = true
  const body = {
    name: form.name.trim(),
    building: form.building.trim() || null,
    room: form.room.trim() || null,
    x: Number(form.x),
    y: Number(form.y),
    notes: form.notes.trim() || null,
  }
  try {
    if (editing.value) {
      await locationsApi.update(editing.value.id, body)
      ui.success(t('loc.updated'))
    } else {
      await locationsApi.create(body)
      ui.success(t('loc.created'))
    }
    dialog.value = false
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    saving.value = false
  }
}

// ---- Delete ---------------------------------------------------------------
const removeLoc = ref<LocationOut | null>(null)
async function confirmRemove() {
  if (!removeLoc.value) return
  try {
    await locationsApi.remove(removeLoc.value.id)
    ui.success(t('loc.deleted'))
    if (selectedId.value === removeLoc.value.id) {
      selectedId.value = null
      selected.value = null
    }
    await load()
  } catch (e) {
    ui.error(e)
  } finally {
    removeLoc.value = null
  }
}

// ---- Map background: draw / move / resize buildings -----------------------
// Geometry is edited directly on the plan (FloorPlanMap emits the new rect);
// name / colour / notes are edited in the side panel.
const BUILDING_PALETTE = [
  '#5b6ef5', '#26a69a', '#e6a532', '#42a5f5', '#7e57c2', '#8a8f9a', '#e5484d', '#2e9e5b',
]
const DEFAULT_BUILDING_COLOR = BUILDING_PALETTE[0]

const mapEdit = ref(false)
const selectedBuildingId = ref<number | null>(null)
const bSaving = ref(false)
const removeBld = ref<MapBuilding | null>(null)
const bForm = reactive({ name: '', color: DEFAULT_BUILDING_COLOR, notes: '' })

const selectedBuilding = computed(
  () => buildings.value.find((b) => b.id === selectedBuildingId.value) ?? null,
)

// Keyed on the id, not the object: dragging a building replaces its entry in
// `buildings`, and that must not wipe a name the user is halfway through typing.
watch(selectedBuildingId, () => {
  const b = selectedBuilding.value
  Object.assign(bForm, {
    name: b?.name ?? '',
    color: b?.color ?? DEFAULT_BUILDING_COLOR,
    notes: b?.notes ?? '',
  })
})

function toggleMapEdit() {
  mapEdit.value = !mapEdit.value
  if (mapEdit.value) {
    dialog.value = false
    picking.value = false
  } else {
    selectedBuildingId.value = null
  }
}

async function onBuildingDraw(rect: { x: number; y: number; width: number; height: number }) {
  bSaving.value = true
  try {
    const created = await mapApi.createBuilding({
      name: t('bld.newName'),
      ...rect,
      color: BUILDING_PALETTE[buildings.value.length % BUILDING_PALETTE.length],
      sort_order: buildings.value.length + 1,
    })
    buildings.value.push(created)
    selectedBuildingId.value = created.id
    ui.success(t('bld.created'))
  } catch (e) {
    ui.error(e)
  } finally {
    bSaving.value = false
  }
}

// Fires on every drag/resize release, so it saves optimistically and stays quiet.
async function onBuildingChange(geo: {
  id: number
  x: number
  y: number
  width: number
  height: number
}) {
  const idx = buildings.value.findIndex((b) => b.id === geo.id)
  if (idx === -1) return
  const previous = buildings.value[idx]
  buildings.value[idx] = { ...previous, ...geo }
  try {
    const { id, ...body } = geo
    buildings.value[idx] = await mapApi.updateBuilding(id, body)
  } catch (e) {
    buildings.value[idx] = previous
    ui.error(e)
  }
}

async function saveBuilding() {
  const b = selectedBuilding.value
  if (!b) return
  if (!bForm.name.trim()) {
    ui.warning(t('loc.nameRequired'))
    return
  }
  bSaving.value = true
  try {
    const saved = await mapApi.updateBuilding(b.id, {
      name: bForm.name.trim(),
      color: bForm.color || null,
      notes: bForm.notes.trim() || null,
    })
    const idx = buildings.value.findIndex((x) => x.id === b.id)
    if (idx !== -1) buildings.value[idx] = saved
    ui.success(t('bld.updated'))
  } catch (e) {
    ui.error(e)
  } finally {
    bSaving.value = false
  }
}

async function confirmRemoveBuilding() {
  if (!removeBld.value) return
  const id = removeBld.value.id
  try {
    await mapApi.removeBuilding(id)
    buildings.value = buildings.value.filter((b) => b.id !== id)
    if (selectedBuildingId.value === id) selectedBuildingId.value = null
    ui.success(t('bld.deleted'))
  } catch (e) {
    ui.error(e)
  } finally {
    removeBld.value = null
  }
}

onMounted(() => {
  load()
  loadBuildings()
})
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader
      :title="$t('nav.locations')"
      :subtitle="$t('loc.subtitle')"
      icon="mdi-map-marker-radius"
    >
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="load" />
        <v-btn
          v-if="auth.canPropose"
          :color="mapEdit ? 'secondary' : undefined"
          :variant="mapEdit ? 'flat' : 'tonal'"
          :prepend-icon="mapEdit ? 'mdi-check' : 'mdi-pencil-ruler'"
          @click="toggleMapEdit"
        >
          {{ mapEdit ? $t('bld.doneEditing') : $t('bld.editMap') }}
        </v-btn>
        <v-btn
          v-if="auth.canPropose"
          color="primary"
          prepend-icon="mdi-map-marker-plus"
          @click="openCreate"
        >
          {{ $t('loc.addLocation') }}
        </v-btn>
      </template>
    </PageHeader>

    <v-row>
      <!-- Map -->
      <v-col cols="12" md="8">
        <v-card variant="flat" border>
          <v-card-title class="d-flex align-center gap-2">
            <v-icon icon="mdi-floor-plan" color="primary" />
            <span class="text-subtitle-1 font-weight-bold">{{ $t('loc.floorPlan') }}</span>
            <v-spacer />
            <v-btn
              v-if="picking"
              size="small"
              variant="text"
              prepend-icon="mdi-close"
              @click="cancelPicking"
            >
              {{ $t('loc.cancelPick') }}
            </v-btn>
          </v-card-title>
          <v-divider />
          <v-card-text>
            <div ref="planAnchor">
            <FloorPlanMap
              :locations="locations"
              :selected-id="selectedId"
              :placing="picking"
              :buildings="buildings"
              :editing="mapEdit"
              :selected-building-id="selectedBuildingId"
              @select="selectLocation"
              @mapclick="onMapPlace"
              @select-building="selectedBuildingId = $event"
              @deselect-building="selectedBuildingId = null"
              @building-draw="onBuildingDraw"
              @building-change="onBuildingChange"
            />
            </div>
            <div class="d-flex flex-wrap gap-4 mt-3 justify-center text-caption text-medium-emphasis">
              <span><v-icon icon="mdi-circle" color="#9aa0b4" size="12" /> {{ $t('loc.legendEmpty') }}</span>
              <span><v-icon icon="mdi-circle" color="#2e9e5b" size="12" /> {{ $t('loc.legend1') }}</span>
              <span><v-icon icon="mdi-circle" color="#e6a532" size="12" /> {{ $t('loc.legend4') }}</span>
              <span><v-icon icon="mdi-circle" color="#e5484d" size="12" /> {{ $t('loc.legend10') }}</span>
              <span><v-icon icon="mdi-circle-outline" color="#26c6da" size="12" /> {{ $t('loc.legendDesiccator') }}</span>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Map editor (edit mode) -->
      <v-col v-if="mapEdit" cols="12" md="4">
        <v-card variant="flat" border height="100%">
          <v-card-title class="d-flex align-center gap-2">
            <v-icon icon="mdi-pencil-ruler" color="secondary" />
            <span class="text-subtitle-1 font-weight-bold">{{ $t('bld.editorTitle') }}</span>
          </v-card-title>
          <v-divider />
          <v-card-text>
            <v-alert type="info" variant="tonal" density="compact" class="mb-4">
              {{ $t('bld.editorHint') }}
            </v-alert>

            <!-- Properties of the selected building -->
            <template v-if="selectedBuilding">
              <v-text-field
                v-model="bForm.name"
                :label="$t('bld.name')"
                density="comfortable"
                class="mb-2"
              />
              <div class="text-caption text-medium-emphasis mb-1">{{ $t('bld.color') }}</div>
              <div class="d-flex flex-wrap gap-2 mb-4">
                <button
                  v-for="c in BUILDING_PALETTE"
                  :key="c"
                  type="button"
                  class="swatch"
                  :class="{ active: bForm.color === c }"
                  :style="{ background: c }"
                  :aria-label="c"
                  @click="bForm.color = c"
                />
              </div>
              <v-textarea
                v-model="bForm.notes"
                :label="$t('bld.notes')"
                rows="2"
                auto-grow
                density="comfortable"
              />
              <div class="text-caption text-medium-emphasis">
                {{ $t('bld.geometry') }}:
                x {{ selectedBuilding.x }} · y {{ selectedBuilding.y }} ·
                {{ selectedBuilding.width }} × {{ selectedBuilding.height }}
              </div>
              <div class="d-flex gap-2 mt-4">
                <v-btn
                  color="primary"
                  variant="flat"
                  :loading="bSaving"
                  prepend-icon="mdi-content-save"
                  @click="saveBuilding"
                >
                  {{ $t('common.save') }}
                </v-btn>
                <v-spacer />
                <v-btn
                  v-if="auth.canDirectEdit"
                  color="error"
                  variant="text"
                  prepend-icon="mdi-delete-outline"
                  @click="removeBld = selectedBuilding"
                >
                  {{ $t('common.delete') }}
                </v-btn>
              </div>
            </template>
            <EmptyState
              v-else
              icon="mdi-vector-square"
              :title="$t('bld.nothingSelected')"
              :text="$t('bld.nothingSelectedHint')"
            />
          </v-card-text>

          <v-divider />
          <v-list-subheader class="text-uppercase text-caption font-weight-bold">
            {{ $t('bld.buildings', { n: buildings.length }) }}
          </v-list-subheader>
          <v-list v-if="buildings.length" density="compact" nav class="py-0">
            <v-list-item
              v-for="b in buildings"
              :key="b.id"
              :active="b.id === selectedBuildingId"
              rounded="lg"
              class="mx-2"
              @click="selectedBuildingId = b.id"
            >
              <template #prepend>
                <span class="swatch sm me-3" :style="{ background: b.color || DEFAULT_BUILDING_COLOR }" />
              </template>
              <v-list-item-title><bdi>{{ b.name }}</bdi></v-list-item-title>
            </v-list-item>
          </v-list>
          <div v-else class="px-4 pb-4 text-caption text-medium-emphasis">
            {{ $t('bld.noBuildings') }}
          </div>
        </v-card>
      </v-col>

      <!-- Selected location items -->
      <v-col v-else cols="12" md="4">
        <v-card variant="flat" border height="100%">
          <template v-if="selected">
            <v-card-title class="d-flex align-center gap-2">
              <v-icon icon="mdi-map-marker" color="primary" />
              <span class="text-subtitle-1 font-weight-bold"><bdi>{{ selected.name }}</bdi></span>
              <v-chip v-if="selected.is_desiccator" size="x-small" color="cyan-darken-2" variant="tonal" prepend-icon="mdi-water-off">
                {{ $t('fieldInput.desiccator') }}
              </v-chip>
            </v-card-title>
            <v-card-subtitle>
              {{ [selected.building, selected.room].filter(Boolean).join(' · ') || $t('loc.noBuildingInfo') }}
            </v-card-subtitle>
            <v-divider />
            <v-card-text v-if="selected.notes" class="text-body-2">{{ selected.notes }}</v-card-text>
            <v-divider v-if="selected.notes" />
            <div v-if="itemsLoading" class="pa-4">
              <v-skeleton-loader type="list-item-two-line@4" />
            </div>
            <v-list v-else-if="items.length" lines="two" density="comfortable">
              <v-list-item
                v-for="it in items"
                :key="it.id"
                @click="router.push(`/items/${it.id}`)"
              >
                <template #prepend>
                  <TypeIcon :type="it.type" :size="22" />
                </template>
                <v-list-item-title class="font-weight-medium"><bdi>{{ it.name }}</bdi></v-list-item-title>
                <v-list-item-subtitle>
                  {{ it.serial }}<span v-if="it.parent_label"> · {{ $t('loc.inside', { parent: it.parent_label }) }}</span>
                </v-list-item-subtitle>
                <template #append>
                  <StateChip :state="it.state" />
                </template>
              </v-list-item>
            </v-list>
            <EmptyState v-else icon="mdi-package-variant" :title="$t('loc.noItemsHere')" />
          </template>
          <EmptyState
            v-else
            icon="mdi-gesture-tap"
            :title="$t('loc.selectTitle')"
            :text="$t('loc.selectHint')"
          />
        </v-card>
      </v-col>
    </v-row>

    <!-- Table -->
    <v-card variant="flat" border class="mt-6">
      <v-data-table
        :headers="headers as any"
        :items="locations"
        :loading="loading"
        item-value="id"
        density="comfortable"
        hover
        @click:row="(_: unknown, ctx: any) => selectLocation(ctx.item.id)"
      >
        <template #item.name="{ item }">
          <span class="font-weight-medium"><bdi>{{ item.name }}</bdi></span>
        </template>
        <template #item.building="{ item }">{{ item.building || '—' }}</template>
        <template #item.room="{ item }">{{ item.room || '—' }}</template>
        <template #item.is_desiccator="{ item }">
          <v-icon v-if="item.is_desiccator" icon="mdi-water-off" color="cyan-darken-2" size="18" />
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.item_count="{ item }">
          <v-chip size="x-small" variant="tonal" color="primary">{{ item.item_count }}</v-chip>
        </template>
        <template #item.actions="{ item }">
          <v-btn
            v-if="auth.canPropose"
            icon="mdi-pencil"
            size="small"
            variant="text"
            @click.stop="openEdit(item)"
          />
          <v-btn
            v-if="auth.canDirectEdit"
            icon="mdi-delete-outline"
            size="small"
            variant="text"
            color="error"
            @click.stop="removeLoc = item"
          />
        </template>
        <template #no-data>
          <EmptyState icon="mdi-map-marker-off" :title="$t('loc.noLocations')" />
        </template>
      </v-data-table>
    </v-card>

    <!-- Create / edit dialog -->
    <v-dialog v-model="dialog" max-width="560">
      <v-card rounded="lg">
        <v-card-title class="pa-4">{{ editing ? $t('loc.editLocation') : $t('loc.addLocation') }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-text-field v-model="form.name" :label="$t('loc.nameReq')" class="mb-1" />
          <v-row dense>
            <v-col cols="6"><v-text-field v-model="form.building" :label="$t('loc.building')" /></v-col>
            <v-col cols="6"><v-text-field v-model="form.room" :label="$t('loc.room')" /></v-col>
          </v-row>
          <v-row dense align="center">
            <v-col cols="4">
              <v-text-field v-model.number="form.x" label="X (0–100)" type="number" min="0" max="100" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model.number="form.y" label="Y (0–100)" type="number" min="0" max="100" />
            </v-col>
            <v-col cols="4">
              <v-btn
                variant="tonal"
                color="primary"
                block
                prepend-icon="mdi-crosshairs-gps"
                @click="startPicking"
              >
                {{ $t('loc.pickOnMap') }}
              </v-btn>
            </v-col>
          </v-row>
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            {{ $t('loc.tip') }}
          </v-alert>
          <v-alert
            v-if="editing?.is_desiccator"
            type="info"
            variant="tonal"
            density="compact"
            class="mb-3"
            icon="mdi-water-off"
          >
            {{ $t('loc.isDesiccator') }}
          </v-alert>
          <v-textarea v-model="form.notes" :label="$t('loc.notes')" rows="2" auto-grow />
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
      :model-value="removeLoc !== null"
      :title="$t('loc.deleteTitle')"
      :message="removeLoc ? $t('loc.deleteMsg', { name: removeLoc.name }) : ''"
      :confirm-text="$t('common.delete')"
      @update:model-value="(v) => !v && (removeLoc = null)"
      @confirm="confirmRemove"
    />

    <ConfirmDialog
      :model-value="removeBld !== null"
      :title="$t('bld.deleteTitle')"
      :message="removeBld ? $t('bld.deleteMsg', { name: removeBld.name }) : ''"
      :confirm-text="$t('common.delete')"
      @update:model-value="(v) => !v && (removeBld = null)"
      @confirm="confirmRemoveBuilding"
    />
  </v-container>
</template>

<style scoped>
.swatch {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 2px solid transparent;
  box-shadow: 0 0 0 1px rgba(128, 128, 128, 0.35) inset;
  cursor: pointer;
}
.swatch.active {
  border-color: rgb(var(--v-theme-on-surface));
}
.swatch.sm {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  cursor: default;
}
</style>
