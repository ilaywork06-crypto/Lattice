import { defineStore } from 'pinia'
import { ref } from 'vue'
import { catalogApi } from '@/api/services'
import type { CatalogCategory, CatalogOption } from '@/api/types'

// Caches the admin-managed vocabularies so every form/filter can offer the
// same dropdowns without re-fetching. Call `ensure()` on mount; `refresh()`
// after an edit in the Catalog admin page.
export const useCatalogStore = defineStore('catalog', () => {
  const projects = ref<CatalogOption[]>([])
  const industries = ref<CatalogOption[]>([])
  const teams = ref<CatalogOption[]>([])
  const loaded = ref(false)
  const loading = ref(false)

  async function refresh() {
    loading.value = true
    try {
      const all = await catalogApi.list()
      projects.value = all
        .filter((o) => o.category === 'project')
        .sort((a, b) => a.sort_order - b.sort_order || a.value.localeCompare(b.value))
      industries.value = all
        .filter((o) => o.category === 'industry')
        .sort((a, b) => a.sort_order - b.sort_order || a.value.localeCompare(b.value))
      teams.value = all
        .filter((o) => o.category === 'team')
        .sort((a, b) => a.sort_order - b.sort_order || a.value.localeCompare(b.value))
      loaded.value = true
    } finally {
      loading.value = false
    }
  }

  async function ensure() {
    if (!loaded.value && !loading.value) await refresh()
  }

  // Active values only — used to populate create/edit dropdowns.
  function activeValues(list: CatalogOption[], current?: string | null): string[] {
    const values = list.filter((o) => o.active).map((o) => o.value)
    // keep a legacy value visible so editing an item doesn't silently drop it
    if (current && !values.includes(current)) values.unshift(current)
    return values
  }

  function byCategory(category: CatalogCategory): CatalogOption[] {
    return category === 'project'
      ? projects.value
      : category === 'industry'
        ? industries.value
        : teams.value
  }

  function byId(id: number): CatalogOption | undefined {
    return [...projects.value, ...industries.value, ...teams.value].find((o) => o.id === id)
  }

  return {
    projects, industries, teams, loaded, loading, refresh, ensure, activeValues, byCategory, byId,
  }
})
