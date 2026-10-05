<script setup lang="ts">
// Every template, by type. Managers create/edit/delete; editors propose.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { templatesApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import TemplateEditorDialog from '@/components/TemplateEditorDialog.vue'
import ProposeChangeDialog from '@/components/ProposeChangeDialog.vue'
import TypeIcon from '@/components/TypeIcon.vue'
import type { ProposeContext } from '@/lib/propose'
import {
  CARD_TYPE_COLORS,
  CARD_TYPE_LABELS,
  ITEM_TYPES,
  TYPE_LABELS,
  formatDate,
} from '@/constants'
import type { ItemType, TemplateCreate, TemplateSummary } from '@/api/types'

const auth = useAuthStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n({ useScope: 'global' })

const NAV_PLURAL: Record<ItemType, string> = {
  setup: 'nav.setups',
  assembly: 'nav.assemblies',
  card: 'nav.cards',
}

const tab = ref<ItemType>((route.query.type as ItemType) || 'card')
const templates = ref<TemplateSummary[]>([])
const loading = ref(false)
const search = ref('')

async function load() {
  loading.value = true
  try {
    templates.value = await templatesApi.list()
  } catch (e) {
    ui.error(e)
  } finally {
    loading.value = false
  }
}

const byId = computed(() => new Map(templates.value.map((tp) => [tp.id, tp])))
const shown = computed(() => templates.value.filter((tp) => tp.type === tab.value))
const countOf = (ty: ItemType) => templates.value.filter((tp) => tp.type === ty).length

const headers = computed(() => {
  const h: Record<string, unknown>[] = [
    { title: t('fields.name'), key: 'name' },
    { title: t('templates.prefix'), key: 'serial_prefix', width: 110 },
  ]
  if (tab.value === 'card') h.push({ title: t('fields.cardType'), key: 'card_type', width: 140 })
  h.push(
    { title: t('templates.fieldCount'), key: 'field_count', align: 'center', width: 100 },
    { title: tab.value === 'card' ? t('templates.usedIn') : t('templates.contains'), key: 'relations', sortable: false },
    { title: t('groups.units'), key: 'counts.total', align: 'center', width: 100 },
    { title: t('fields.updatedAt'), key: 'updated_at', width: 130 },
  )
  return h
})

function relationNames(tp: TemplateSummary): string[] {
  const ids = tp.type === 'card' ? tp.parent_template_ids : tp.child_template_ids
  return ids.map((id) => byId.value.get(id)?.name).filter(Boolean) as string[]
}

watch(tab, (v) => router.replace({ query: { ...route.query, type: v } }))

// ── create (direct or proposal) ──
const editorOpen = ref(false)
const proposeOpen = ref(false)
const proposeCtx = ref<ProposeContext | null>(null)

async function onSubmit(payload: TemplateCreate | Partial<TemplateCreate>) {
  const body = payload as TemplateCreate
  if (auth.canDirectEdit) {
    try {
      const created = await templatesApi.create(body)
      ui.success(t('templates.created'))
      editorOpen.value = false
      router.push(`/templates/${created.id}`)
    } catch (e) {
      ui.error(e)
    }
    return
  }
  editorOpen.value = false
  proposeCtx.value = {
    action: 'template_create',
    itemType: body.type,
    payload: body as unknown as Record<string, unknown>,
    targetName: body.name,
    summaryLines: [
      { label: t('fields.type'), value: TYPE_LABELS[body.type] },
      { label: t('fields.name'), value: body.name },
      { label: t('templates.prefix'), value: body.serial_prefix },
      { label: t('templates.fieldCount'), value: String(body.fields.length) },
    ],
  }
  proposeOpen.value = true
}

onMounted(load)
</script>

<template>
  <v-container fluid class="pa-4 pa-md-6">
    <PageHeader :title="$t('nav.templates')" :subtitle="$t('templates.subtitle')" icon="mdi-shape-outline">
      <template #actions>
        <v-btn variant="tonal" icon="mdi-refresh" :loading="loading" @click="load" />
        <v-btn
          v-if="auth.canPropose"
          color="primary"
          :prepend-icon="auth.canDirectEdit ? 'mdi-plus' : 'mdi-file-plus-outline'"
          @click="editorOpen = true"
        >
          {{ auth.canDirectEdit ? $t('templates.new') : $t('templates.propose') }}
        </v-btn>
      </template>
    </PageHeader>

    <v-card variant="flat" border>
      <v-tabs v-model="tab" color="primary">
        <v-tab v-for="ty in ITEM_TYPES" :key="ty" :value="ty">
          <TypeIcon :type="ty" class="me-2" />
          {{ $t(NAV_PLURAL[ty]) }}
          <v-chip size="x-small" variant="tonal" class="ms-2">{{ countOf(ty) }}</v-chip>
        </v-tab>
      </v-tabs>
      <v-divider />
      <v-alert type="info" variant="tonal" density="compact" class="ma-4" icon="mdi-information-outline">
        {{ $t('templates.explainer') }}
      </v-alert>
      <div class="px-4 pb-2">
        <v-text-field
          v-model="search"
          :label="$t('common.search')"
          prepend-inner-icon="mdi-magnify"
          clearable
          hide-details
          density="comfortable"
          style="max-width: 320px"
        />
      </div>
      <v-data-table
        :headers="headers as any"
        :items="shown"
        :loading="loading"
        :search="search"
        item-value="id"
        hover
        density="comfortable"
        :items-per-page="25"
        @click:row="(_: unknown, ctx: any) => router.push(`/templates/${ctx.item.id}`)"
      >
        <template #item.name="{ item }">
          <div class="font-weight-medium">{{ item.name }}</div>
          <div v-if="item.description" class="text-caption text-medium-emphasis text-truncate" style="max-width: 360px">
            {{ item.description }}
          </div>
        </template>
        <template #item.serial_prefix="{ item }">
          <v-chip size="small" variant="outlined" label>{{ item.serial_prefix }}</v-chip>
        </template>
        <template #item.card_type="{ item }">
          <v-chip v-if="item.card_type" :color="CARD_TYPE_COLORS[item.card_type]" size="small" variant="flat" label>
            {{ CARD_TYPE_LABELS[item.card_type] }}
          </v-chip>
        </template>
        <template #item.relations="{ item }">
          <div class="d-flex flex-wrap gap-1">
            <v-chip v-for="n in relationNames(item).slice(0, 3)" :key="n" size="x-small" variant="tonal">{{ n }}</v-chip>
            <v-chip v-if="relationNames(item).length > 3" size="x-small" variant="text">
              +{{ relationNames(item).length - 3 }}
            </v-chip>
            <span v-if="!relationNames(item).length" class="text-medium-emphasis">—</span>
          </div>
        </template>
        <template #item.counts.total="{ item }">
          <v-chip size="small" variant="tonal" color="primary">{{ item.counts.total }}</v-chip>
        </template>
        <template #item.updated_at="{ item }">
          <span class="text-caption">{{ formatDate(item.updated_at) }}</span>
        </template>
        <template #no-data>
          <EmptyState icon="mdi-shape-outline" :title="$t('templates.empty')" :text="$t('templates.emptyHint')" />
        </template>
      </v-data-table>
    </v-card>

    <TemplateEditorDialog
      v-model="editorOpen"
      :type="tab"
      :direct="auth.canDirectEdit"
      @submit="onSubmit"
    />
    <ProposeChangeDialog v-model="proposeOpen" :context="proposeCtx" />
  </v-container>
</template>
