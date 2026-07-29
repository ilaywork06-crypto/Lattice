import { defineStore } from 'pinia'
import { authApi } from '@/api/services'
import {
  clearToken,
  registerUnauthorizedHandler,
  setToken,
} from '@/api/client'
import type { UserRole } from '@/api/types'
import { router } from '@/router'

const KEYS = {
  role: 'lattice.role',
  fullName: 'lattice.full_name',
  userId: 'lattice.user_id',
}

interface AuthState {
  token: string | null
  role: UserRole | null
  fullName: string | null
  userId: number | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: localStorage.getItem('lattice.access_token'),
    role: (localStorage.getItem(KEYS.role) as UserRole | null) ?? null,
    fullName: localStorage.getItem(KEYS.fullName),
    userId: localStorage.getItem(KEYS.userId)
      ? Number(localStorage.getItem(KEYS.userId))
      : null,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    isManager: (state) => state.role === 'manager',
    isEditor: (state) => state.role === 'editor',
    isViewer: (state) => state.role === 'viewer',
    // Managers act directly on item endpoints; everyone else proposes changes.
    canDirectEdit: (state) => state.role === 'manager',
    // Editors + managers may submit change-requests / create locations+thresholds.
    canPropose: (state) => state.role === 'editor' || state.role === 'manager',
    initials(state): string {
      if (!state.fullName) return '?'
      return state.fullName
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((p) => p[0]?.toUpperCase())
        .join('')
    },
  },
  actions: {
    async login(email: string, password: string) {
      const res = await authApi.login(email, password)
      this.token = res.access_token
      this.role = res.role
      this.fullName = res.full_name
      this.userId = res.user_id
      setToken(res.access_token)
      localStorage.setItem(KEYS.role, res.role)
      localStorage.setItem(KEYS.fullName, res.full_name)
      localStorage.setItem(KEYS.userId, String(res.user_id))
    },
    logout(redirect = true) {
      this.token = null
      this.role = null
      this.fullName = null
      this.userId = null
      clearToken()
      localStorage.removeItem(KEYS.role)
      localStorage.removeItem(KEYS.fullName)
      localStorage.removeItem(KEYS.userId)
      if (redirect && router.currentRoute.value.name !== 'login') {
        router.push({ name: 'login' })
      }
    },
  },
})

// Wire the 401 interceptor to the store once at module load.
export function installAuthInterceptor() {
  registerUnauthorizedHandler(() => {
    const store = useAuthStore()
    if (store.isAuthenticated) {
      store.logout(true)
    }
  })
}
