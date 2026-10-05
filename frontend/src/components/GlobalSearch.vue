<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { searchApi } from '@/api/services'
import StateChip from '@/components/StateChip.vue'
import { ROLE_LABELS, TYPE_COLORS, TYPE_ICONS, TYPE_LABELS } from '@/constants'
import type { ItemType, SearchHit, SearchResults } from '@/api/types'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [v: boolean] }>()

const router = useRouter()
const { t: i18nT } = useI18n({ useScope: 'global' })

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const query = ref('')
const loading = ref(false)
const results = ref<SearchResults | null>(null)
const activeIndex = ref(0)
const inputRef = ref()
let timer: ReturnType<typeof setTimeout> | null = null
let reqId = 0

// One flat list so the arrow keys can move through every group in order.
const flatHits = computed<SearchHit[]>(() => {
  const r = results.value
  if (!r) return []
  return [...r.items, ...r.templates, ...r.locations, ...r.users]
})

function reset() {
  query.value = ''
  results.value = null
  activeIndex.value = 0
}

watch(open, (v) => {
  if (v) {
    reset()
    nextTick(() => inputRef.value?.focus())
  }
})

watch(query, (q) => {
  if (timer) clearTimeout(timer)
  activeIndex.value = 0
  const term = q.trim()
  if (!term) {
    results.value = null
    loading.value = false
    return
  }
  loading.value = true
  timer = setTimeout(() => void run(term), 220)
})

async function run(term: string) {
  const id = ++reqId
  try {
    const res = await searchApi.query(term)
    if (id === reqId) results.value = res
  } catch {
    if (id === reqId) results.value = null
  } finally {
    if (id === reqId) loading.value = false
  }
}

function hitIcon(hit: SearchHit): string {
  if (hit.kind === 'item') return TYPE_ICONS[(hit.badge ?? 'card') as ItemType]
  if (hit.kind === 'template') return 'mdi-shape-outline'
  if (hit.kind === 'location') return 'mdi-map-marker'
  return 'mdi-account'
}
function hitColor(hit: SearchHit): string {
  if (hit.kind === 'item' || hit.kind === 'template') {
    return TYPE_COLORS[(hit.badge ?? 'card') as ItemType]
  }
  if (hit.kind === 'location') return 'blue-grey'
  return 'deep-purple'
}
function hitBadge(hit: SearchHit): string {
  if (hit.kind === 'item') return TYPE_LABELS[(hit.badge ?? 'card') as ItemType]
  if (hit.kind === 'template') {
    return `${TYPE_LABELS[(hit.badge ?? 'card') as ItemType]} · ${i18nT('search.templateBadge')}`
  }
  if (hit.kind === 'user' && hit.badge) return ROLE_LABELS[hit.badge as 'viewer' | 'editor' | 'manager']
  return ''
}

function go(hit: SearchHit | undefined) {
  if (!hit) return
  open.value = false
  router.push(hit.link)
}

function onEnter() {
  go(flatHits.value[activeIndex.value])
}
function move(delta: number) {
  const n = flatHits.value.length
  if (!n) return
  activeIndex.value = (activeIndex.value + delta + n) % n
}
function indexOfHit(hit: SearchHit): number {
  return flatHits.value.indexOf(hit)
}
</script>

<template>
  <v-dialog v-model="open" max-width="640" scrollable transition="dialog-top-transition">
    <v-card rounded="lg" class="global-search">
      <div class="pa-3 pb-0">
        <v-text-field
          ref="inputRef"
          v-model="query"
          :placeholder="$t('search.placeholder')"
          prepend-inner-icon="mdi-magnify"
          variant="solo-filled"
          flat
          hide-details
          clearable
          autofocus
          :loading="loading"
          @keydown.down.prevent="move(1)"
          @keydown.up.prevent="move(-1)"
          @keydown.enter.prevent="onEnter"
          @keydown.esc="open = false"
        />
      </div>

      <v-card-text class="pt-2" style="min-height: 120px; max-height: 60vh">
        <!-- Empty / hint -->
        <div v-if="!query.trim()" class="text-center text-medium-emphasis py-8">
          <v-icon icon="mdi-magnify" size="40" class="mb-2 d-block mx-auto" />
          <div class="text-body-2">{{ $t('search.hint') }}</div>
          <div class="text-caption mt-1">{{ $t('search.hintKeys') }}</div>
        </div>

        <div v-else-if="!loading && results && results.total === 0" class="text-center text-medium-emphasis py-8">
          <v-icon icon="mdi-file-search-outline" size="40" class="mb-2 d-block mx-auto" />
          <div class="text-body-2">{{ $t('search.noResults', { q: query }) }}</div>
        </div>

        <template v-else-if="results">
          <!-- Items -->
          <template v-if="results.items.length">
            <div class="text-overline text-medium-emphasis px-2 pt-2">{{ $t('search.groupItems') }}</div>
            <v-list density="comfortable" nav>
              <v-list-item
                v-for="hit in results.items"
                :key="'i' + hit.id"
                :active="indexOfHit(hit) === activeIndex"
                rounded="lg"
                @click="go(hit)"
                @mouseenter="activeIndex = indexOfHit(hit)"
              >
                <template #prepend>
                  <v-icon :icon="hitIcon(hit)" :color="hitColor(hit)" />
                </template>
                <v-list-item-title class="font-weight-medium">{{ hit.title }}</v-list-item-title>
                <v-list-item-subtitle v-if="hit.subtitle">{{ hit.subtitle }}</v-list-item-subtitle>
                <template #append>
                  <StateChip v-if="hit.state" :state="hit.state" />
                  <v-chip size="x-small" variant="tonal" class="ms-2">{{ hitBadge(hit) }}</v-chip>
                </template>
              </v-list-item>
            </v-list>
          </template>

          <!-- Templates -->
          <template v-if="results.templates.length">
            <div class="text-overline text-medium-emphasis px-2 pt-2">{{ $t('search.groupTemplates') }}</div>
            <v-list density="comfortable" nav>
              <v-list-item
                v-for="hit in results.templates"
                :key="'t' + hit.id"
                :active="indexOfHit(hit) === activeIndex"
                rounded="lg"
                @click="go(hit)"
                @mouseenter="activeIndex = indexOfHit(hit)"
              >
                <template #prepend>
                  <v-icon :icon="hitIcon(hit)" :color="hitColor(hit)" />
                </template>
                <v-list-item-title class="font-weight-medium">{{ hit.title }}</v-list-item-title>
                <v-list-item-subtitle v-if="hit.subtitle">{{ hit.subtitle }}</v-list-item-subtitle>
                <template #append>
                  <v-chip size="x-small" variant="tonal">{{ hitBadge(hit) }}</v-chip>
                </template>
              </v-list-item>
            </v-list>
          </template>

          <!-- Locations -->
          <template v-if="results.locations.length">
            <div class="text-overline text-medium-emphasis px-2 pt-2">{{ $t('search.groupLocations') }}</div>
            <v-list density="comfortable" nav>
              <v-list-item
                v-for="hit in results.locations"
                :key="'l' + hit.id"
                :active="indexOfHit(hit) === activeIndex"
                rounded="lg"
                @click="go(hit)"
                @mouseenter="activeIndex = indexOfHit(hit)"
              >
                <template #prepend>
                  <v-icon :icon="hitIcon(hit)" :color="hitColor(hit)" />
                </template>
                <v-list-item-title class="font-weight-medium">{{ hit.title }}</v-list-item-title>
                <v-list-item-subtitle v-if="hit.subtitle">{{ hit.subtitle }}</v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </template>

          <!-- Users -->
          <template v-if="results.users.length">
            <div class="text-overline text-medium-emphasis px-2 pt-2">{{ $t('search.groupUsers') }}</div>
            <v-list density="comfortable" nav>
              <v-list-item
                v-for="hit in results.users"
                :key="'u' + hit.id"
                :active="indexOfHit(hit) === activeIndex"
                rounded="lg"
                @click="go(hit)"
                @mouseenter="activeIndex = indexOfHit(hit)"
              >
                <template #prepend>
                  <v-icon :icon="hitIcon(hit)" :color="hitColor(hit)" />
                </template>
                <v-list-item-title class="font-weight-medium">{{ hit.title }}</v-list-item-title>
                <v-list-item-subtitle v-if="hit.subtitle">{{ hit.subtitle }}</v-list-item-subtitle>
                <template #append>
                  <v-chip size="x-small" variant="tonal">{{ hitBadge(hit) }}</v-chip>
                </template>
              </v-list-item>
            </v-list>
          </template>
        </template>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.global-search :deep(.v-list-item--active) {
  background: rgb(var(--v-theme-primary), 0.12);
}
</style>
