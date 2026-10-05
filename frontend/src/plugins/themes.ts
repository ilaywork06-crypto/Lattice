import type { ThemeDefinition } from 'vuetify'

// The app's colour themes. The two originals stay; the rest are pastel —
// soft backgrounds with a slightly deeper accent of the same hue so buttons
// and chips keep readable contrast (Vuetify derives each `on-*` text colour
// from the background's luminance).

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

function pastel(
  background: string,
  surfaceVariant: string,
  primary: string,
  secondary: string,
  accent: string,
): ThemeDefinition {
  return {
    dark: false,
    colors: {
      background,
      surface: '#ffffff',
      'surface-variant': surfaceVariant,
      'on-surface-variant': '#4a4658',
      primary,
      secondary,
      accent,
      success: '#5fae7f',
      info: '#6b9bd6',
      warning: '#d9a441',
      error: '#d9666b',
    },
  }
}

const pastelLavender = pastel('#f6f3fc', '#ebe4f7', '#8c7ad1', '#b39ddb', '#80cbc4')
const pastelMint = pastel('#f1faf6', '#dff2e9', '#4fa98a', '#8fcfb6', '#9fa8da')
const pastelPeach = pastel('#fff6f1', '#fbe6da', '#e08a6a', '#f2b8a0', '#90caf9')
const pastelSky = pastel('#f2f8fd', '#dfedf9', '#5e9ad6', '#a3c9ef', '#f48fb1')
const pastelRose = pastel('#fdf3f6', '#f8e1e8', '#d1709a', '#eda7c2', '#81d4fa')
const pastelLemon = pastel('#fdfbee', '#f4efcf', '#b99b2d', '#e3d07a', '#a5d6a7')
const pastelLilacNight: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#1c1a26',
    surface: '#252232',
    'surface-variant': '#322e43',
    'on-surface-variant': '#d9d3ee',
    primary: '#b9a7f2',
    secondary: '#a8c6e8',
    accent: '#9fe0cf',
    success: '#9fdcb4',
    info: '#a3c6f2',
    warning: '#f2d49b',
    error: '#f2a3b0',
  },
}
const pastelMintNight: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#161f1d',
    surface: '#1e2a27',
    'surface-variant': '#2a3a36',
    'on-surface-variant': '#cfe8e0',
    primary: '#8fdcc0',
    secondary: '#b7d8f0',
    accent: '#f5c2d6',
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
