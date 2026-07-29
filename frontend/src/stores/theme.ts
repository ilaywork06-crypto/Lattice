import { defineStore } from 'pinia'

const THEME_KEY = 'lattice.theme'

type ThemeName = 'latticeLight' | 'latticeDark'

function initialTheme(): ThemeName {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored === 'latticeLight' || stored === 'latticeDark') return stored
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
    isDark: (state) => state.current === 'latticeDark',
  },
  actions: {
    toggle() {
      this.current = this.current === 'latticeDark' ? 'latticeLight' : 'latticeDark'
      localStorage.setItem(THEME_KEY, this.current)
    },
    set(name: ThemeName) {
      this.current = name
      localStorage.setItem(THEME_KEY, name)
    },
  },
})
