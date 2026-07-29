import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify, type ThemeDefinition } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'
import { createVueI18nAdapter } from 'vuetify/locale/adapters/vue-i18n'
import { useI18n } from 'vue-i18n'
import { i18n } from '@/i18n'

const latticeLight: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#f4f5fb',
    surface: '#ffffff',
    'surface-variant': '#e9eaf3',
    'on-surface-variant': '#44475a',
    primary: '#5b6ef5',
    secondary: '#7b8794',
    accent: '#00bcd4',
    success: '#2e9e5b',
    info: '#2f80ed',
    warning: '#e6a532',
    error: '#e5484d',
  },
}

const latticeDark: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0f1117',
    surface: '#171a23',
    'surface-variant': '#242836',
    'on-surface-variant': '#c4c7d4',
    primary: '#7c8cff',
    secondary: '#95a1b1',
    accent: '#28d1e6',
    success: '#3ecf7a',
    info: '#4a94ff',
    warning: '#f0b64a',
    error: '#ff6169',
  },
}

export const vuetify = createVuetify({
  // Vuetify reads its locale + RTL direction from vue-i18n via the adapter;
  // switching the vue-i18n locale to `he` flips the whole app to RTL.
  locale: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    adapter: createVueI18nAdapter({ i18n: i18n as any, useI18n }),
    rtl: { he: true, en: false },
  },
  theme: {
    defaultTheme: 'latticeLight',
    themes: { latticeLight, latticeDark },
  },
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
  defaults: {
    VCard: { rounded: 'lg' },
    VBtn: { rounded: 'lg', class: 'text-none' },
    VTextField: { variant: 'outlined', density: 'comfortable', color: 'primary' },
    VTextarea: { variant: 'outlined', density: 'comfortable', color: 'primary' },
    VSelect: { variant: 'outlined', density: 'comfortable', color: 'primary' },
    VAutocomplete: { variant: 'outlined', density: 'comfortable', color: 'primary' },
    VCombobox: { variant: 'outlined', density: 'comfortable', color: 'primary' },
    VChip: { rounded: 'lg' },
    VList: { density: 'comfortable' },
  },
})
