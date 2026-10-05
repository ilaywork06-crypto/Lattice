import { defineStore } from 'pinia'
import { THEMES, THEME_LIST, isThemeName, type ThemeName } from '@/plugins/themes'

const THEME_KEY = 'lattice.theme'

function readStored(): string | null {
  try {
    return localStorage.getItem(THEME_KEY)
  } catch {
    return null
  }
}

function initialTheme(): ThemeName {
  const stored = readStored()
  if (isThemeName(stored)) return stored
  const prefersDark =
    typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  return prefersDark ? 'latticeDark' : 'latticeLight'
}

export const useThemeStore = defineStore('theme', {
  state: (): { current: ThemeName } => ({
    current: initialTheme(),
  }),
  getters: {
    isDark: (state) => !!THEMES[state.current].dark,
    available: () => THEME_LIST,
  },
  actions: {
    /** Flip between the light and dark variant of the default palette. */
    toggle() {
      this.set(this.isDark ? 'latticeLight' : 'latticeDark')
    },
    set(name: ThemeName) {
      this.current = name
      try {
        localStorage.setItem(THEME_KEY, name)
      } catch {
        // storage unavailable (private mode) — the choice lasts for the session
      }
    },
  },
})
