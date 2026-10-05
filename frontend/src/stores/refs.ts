import { defineStore } from 'pinia'
import { ref } from 'vue'
import { locationsApi, usersApi } from '@/api/services'
import type { LocationOut, User, UserBrief } from '@/api/types'

// Reference lists that many forms pick from (users, managers, locations).
// Cached once per session; `refresh()` after editing one of them.
export const useRefsStore = defineStore('refs', () => {
  const users = ref<User[]>([])
  const managers = ref<UserBrief[]>([])
  const locations = ref<LocationOut[]>([])
  const loaded = ref(false)
  let pending: Promise<void> | null = null

  async function refresh() {
    const [u, m, l] = await Promise.all([
      usersApi.list(),
      usersApi.managers(),
      locationsApi.list(),
    ])
    users.value = u.filter((x) => x.is_active)
    managers.value = m
    locations.value = l
    loaded.value = true
  }

  async function ensure() {
    if (loaded.value) return
    if (!pending) pending = refresh().finally(() => (pending = null))
    await pending
  }

  async function refreshLocations() {
    locations.value = await locationsApi.list()
  }

  return { users, managers, locations, loaded, ensure, refresh, refreshLocations }
})
