import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'
import { createVueI18nAdapter } from 'vuetify/locale/adapters/vue-i18n'
import { useI18n } from 'vue-i18n'
import { i18n } from '@/i18n'
import { THEMES } from './themes'

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
    themes: THEMES,
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
