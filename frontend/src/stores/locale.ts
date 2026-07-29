import { defineStore } from 'pinia'
import {
  AVAILABLE_LOCALES,
  applyDocumentLocale,
  i18n,
  initialLocale,
  isRtl,
  persistLocale,
  type LocaleCode,
} from '@/i18n'

export const useLocaleStore = defineStore('locale', {
  state: (): { current: LocaleCode } => ({ current: initialLocale() }),
  getters: {
    isRtl: (state) => isRtl(state.current),
    available: () => AVAILABLE_LOCALES,
  },
  actions: {
    set(code: LocaleCode) {
      this.current = code
      // vue-i18n drives both the app strings and (via the adapter) Vuetify +
      // RTL direction; applyDocumentLocale keeps <html dir/lang> in sync.
      ;(i18n.global.locale as unknown as { value: LocaleCode }).value = code
      applyDocumentLocale(code)
      persistLocale(code)
    },
  },
})
