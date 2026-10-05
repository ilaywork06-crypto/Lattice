import type { ThemeDefinition } from 'vuetify'

// The app's colour themes. The two originals stay; the rest are pastel —
// every surface (page, cards, app bar, drawer) carries the theme's hue so the
// choice is obvious at a glance, with a deeper accent of the same hue so
// buttons and chips keep readable contrast (Vuetify derives each `on-*` text
// colour from the background's luminance).

export interface ThemeMeta {
  name: ThemeName
  /** i18n key under `themes.` */
  label: string
  dark: boolean
  /** Swatch colours for the picker: background, primary, secondary. */
  swatch: [string, string, string]
}

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

function pastel(c: {
  background: string
  surface: string
  surfaceVariant: string
  onSurfaceVariant: string
  primary: string
  secondary: string
  accent: string
}): ThemeDefinition {
  return {
    dark: false,
    colors: {
      background: c.background,
      surface: c.surface,
      'surface-variant': c.surfaceVariant,
      'on-surface-variant': c.onSurfaceVariant,
      primary: c.primary,
      secondary: c.secondary,
      accent: c.accent,
      success: '#5fae7f',
      info: '#6b9bd6',
      warning: '#d9a441',
      error: '#d9666b',
    },
  }
}

const pastelLavender = pastel({
  background: '#e9dffb',
  surface: '#faf7ff',
  surfaceVariant: '#d8c7f4',
  onSurfaceVariant: '#473762',
  primary: '#724acf',
  secondary: '#bb85d6',
  accent: '#40bfae',
})
const pastelMint = pastel({
  background: '#d3f3e4',
  surface: '#f6fdfa',
  surfaceVariant: '#b7e6d0',
  onSurfaceVariant: '#2b5040',
  primary: '#238b68',
  secondary: '#5cbca4',
  accent: '#818cda',
})
const pastelPeach = pastel({
  background: '#ffe2d1',
  surface: '#fffbf7',
  surfaceVariant: '#f9ceb8',
  onSurfaceVariant: '#674232',
  primary: '#db4f24',
  secondary: '#ee9d63',
  accent: '#51a3ec',
})
const pastelSky = pastel({
  background: '#d5e9fc',
  surface: '#f7fcff',
  surfaceVariant: '#bad8f3',
  onSurfaceVariant: '#2e4660',
  primary: '#2f75c6',
  secondary: '#54aed4',
  accent: '#e96793',
})
const pastelRose = pastel({
  background: '#fcdee8',
  surface: '#fff7fa',
  surfaceVariant: '#f3c8d7',
  onSurfaceVariant: '#633649',
  primary: '#c93673',
  secondary: '#da81b5',
  accent: '#3eb6ea',
})
const pastelLemon = pastel({
  background: '#fcf1ba',
  surface: '#fffdf2',
  surfaceVariant: '#f1e09d',
  onSurfaceVariant: '#564725',
  primary: '#a57412',
  secondary: '#dab22f',
  accent: '#56b359',
})
const pastelLilacNight: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#1d172c',
    surface: '#28203c',
    'surface-variant': '#3b3055',
    'on-surface-variant': '#dfd6f5',
    primary: '#b497f7',
    secondary: '#a0c7ee',
    accent: '#8de2cd',
    success: '#9fdcb4',
    info: '#a3c6f2',
    warning: '#f2d49b',
    error: '#f2a3b0',
  },
}
const pastelMintNight: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#10231e',
    surface: '#1a322c',
    'surface-variant': '#284840',
    'on-surface-variant': '#d3eee5',
    primary: '#6adcb2',
    secondary: '#a0cdee',
    accent: '#f6accb',
    success: '#a3e0b2',
    info: '#9ec7ef',
    warning: '#f0d39a',
    error: '#f0a5ad',
  },
}

export const THEMES = {
  latticeLight,
  latticeDark,
  pastelLavender,
  pastelMint,
  pastelPeach,
  pastelSky,
  pastelRose,
  pastelLemon,
  pastelLilacNight,
  pastelMintNight,
}

export type ThemeName = keyof typeof THEMES

export const THEME_LIST: ThemeMeta[] = (Object.keys(THEMES) as ThemeName[]).map((name) => {
  const def = THEMES[name]
  const c = def.colors ?? {}
  return {
    name,
    label: name,
    dark: !!def.dark,
    swatch: [c.background as string, c.primary as string, c.secondary as string],
  }
})

export function isThemeName(value: unknown): value is ThemeName {
  return typeof value === 'string' && value in THEMES
}
