<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
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

async function selectLocation(id: number) {
  selectedId.value = id
  selected.value = locations.value.find((l) => l.id === id) ?? null
  itemsLoading.value = true
  try {
    items.value = await itemsApi.list({ location_id: id, limit: 200 })
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
  dialog.value = true
}
function openEdit(loc: LocationOut) {
  editing.value = loc
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
function onMapPlace(coords: { x: number; y: number }) {
  if (!dialog.value) return
  form.x = coords.x
  form.y = coords.y
}

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

onMounted(load)
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
      <v-col cols="12" md="7">
        <v-card variant="flat" border>
          <v-card-title class="d-flex align-center gap-2">
            <v-icon icon="mdi-floor-plan" color="primary" />
            <span class="text-subtitle-1 font-weight-bold">{{ $t('loc.floorPlan') }}</span>
          </v-card-title>
          <v-divider />
          <v-card-text>
            <FloorPlanMap
              :locations="locations"
              :selected-id="selectedId"
              :placing="dialog"
              @select="selectLocation"
              @mapclick="onMapPlace"
            />
            <div class="d-flex flex-wrap gap-4 mt-3 justify-center text-caption text-medium-emphasis">
              <span><v-icon icon="mdi-circle" color="#9aa0b4" size="12" /> {{ $t('loc.legendEmpty') }}</span>
              <span><v-icon icon="mdi-circle" color="#2e9e5b" size="12" /> {{ $t('loc.legend1') }}</span>
              <span><v-icon icon="mdi-circle" color="#e6a532" size="12" /> {{ $t('loc.legend4') }}</span>
              <span><v-icon icon="mdi-circle" color="#e5484d" size="12" /> {{ $t('loc.legend10') }}</span>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Selected location items -->
      <v-col cols="12" md="5">
        <v-card variant="flat" border height="100%">
          <template v-if="selected">
            <v-card-title class="d-flex align-center gap-2">
              <v-icon icon="mdi-map-marker" color="primary" />
              <span class="text-subtitle-1 font-weight-bold">{{ selected.name }}</span>
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
                <v-list-item-title class="font-weight-medium">{{ it.name }}</v-list-item-title>
                <v-list-item-subtitle>{{ it.project || it.industry || '—' }}</v-list-item-subtitle>
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
          <span class="font-weight-medium">{{ item.name }}</span>
        </template>
        <template #item.building="{ item }">{{ item.building || '—' }}</template>
        <template #item.room="{ item }">{{ item.room || '—' }}</template>
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
          <v-row dense>
            <v-col cols="6">
              <v-text-field v-model.number="form.x" label="X (0–100)" type="number" min="0" max="100" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model.number="form.y" label="Y (0–100)" type="number" min="0" max="100" />
            </v-col>
          </v-row>
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            {{ $t('loc.tip') }}
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
  </v-container>
</template>
