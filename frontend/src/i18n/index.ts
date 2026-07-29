import { createI18n } from 'vue-i18n'
import { en as vuetifyEn, he as vuetifyHe } from 'vuetify/locale'
import en from './en'
import he from './he'

export type LocaleCode = 'en' | 'he'

export const AVAILABLE_LOCALES: { code: LocaleCode; native: string; flag: string }[] = [
  { code: 'en', native: 'English', flag: '🇬🇧' },
  { code: 'he', native: 'עברית', flag: '🇮🇱' },
]

// Locales that render right-to-left.
export const RTL_LOCALES: LocaleCode[] = ['he']

const LOCALE_KEY = 'lattice.locale'

export function isRtl(code: LocaleCode): boolean {
  return RTL_LOCALES.includes(code)
}

export function initialLocale(): LocaleCode {
  const stored = localStorage.getItem(LOCALE_KEY)
  if (stored === 'en' || stored === 'he') return stored
  const nav = (navigator.language || 'en').toLowerCase()
  return nav.startsWith('he') || nav.startsWith('iw') ? 'he' : 'en'
}

export function persistLocale(code: LocaleCode): void {
  localStorage.setItem(LOCALE_KEY, code)
}

/** Reflect the locale on <html> so native elements, CSS `[dir]` and the
 *  document language track the choice. */
export function applyDocumentLocale(code: LocaleCode): void {
  const el = document.documentElement
  el.setAttribute('lang', code)
  el.setAttribute('dir', isRtl(code) ? 'rtl' : 'ltr')
}

export const i18n = createI18n({
  legacy: false, // Composition API mode — required by the Vuetify vue-i18n adapter
  globalInjection: true, // expose $t/$rt in every template
  locale: initialLocale(),
  fallbackLocale: 'en',
  // Vuetify's own component strings (data tables, pagination…) live under
  // `$vuetify`; merging them here lets the adapter localize Vuetify too.
  messages: {
    en: { ...en, $vuetify: vuetifyEn },
    he: { ...he, $vuetify: vuetifyHe },
  },
})

// Ensure <html dir/lang> is correct on first paint.
applyDocumentLocale(initialLocale())
