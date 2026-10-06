import type { ThemeDefinition } from 'vuetify'
import { oklch, readableOn, rgba, withContrast } from '@/lib/color'

// The app's colour themes. The two originals stay; the rest are pastel, and a
// pastel theme is the whole interface in its hue, not a tinted page behind
// white cards: page, cards, dialogs, menus, drawer, app bar, borders, shadows
// and even the text carry it. Each is generated from a few hues by `pastel()` /
// `pastelNight()`, so they share one structure:
//
//   app bar ─ page background ── soft pastel
//   drawer ───────────────────── a deeper band of the same pastel
//   cards, dialogs, menus ────── a light tint that lifts off the page
//   text, borders, shadows ───── deep shades of the hue instead of black/grey
//   primary ──────────────────── a strong shade of the hue
//   secondary, accent ────────── harmonising hues, equally strong
//
// Every foreground colour is checked against WCAG contrast (`withContrast`):
// primary, secondary, accent and the status colours reach 4.5:1 on the page
// itself (warning instead guarantees 4.5:1 for the ink drawn on it), and the
// text drawn on each (`on-*`) is whichever of white or the theme's ink reads
// better.

export interface ThemeMeta {
  name: ThemeName
  /** i18n key under `themes.` */
  label: string
  dark: boolean
  /** Swatch colours for the picker: background, primary, secondary. */
  swatch: [string, string, string]
}

// Extra roles beyond Vuetify's own, given by every theme: the navigation drawer
// and the app bar. In the originals both are the card surface; a pastel theme
// sets them apart so the frame of the app carries the hue too.
const latticeLight: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#f4f5fb',
    surface: '#ffffff',
    'surface-variant': '#e9eaf3',
    'on-surface-variant': '#44475a',
    nav: '#ffffff',
    'app-bar': '#ffffff',
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
    nav: '#171a23',
    'app-bar': '#171a23',
    primary: '#7c8cff',
    secondary: '#95a1b1',
    accent: '#28d1e6',
    success: '#3ecf7a',
    info: '#4a94ff',
    warning: '#f0b64a',
    error: '#ff6169',
  },
}

interface PastelSpec {
  /** The theme's hue (OKLCH degrees): every surface, border and text colour. */
  hue: number
  /** Hue of the primary colour, when it should differ from the tint — a deep
   *  yellow reads as olive, so Lemon's primary is a deep amber. */
  primaryHue?: number
  secondaryHue: number
  accentHue: number
  /** Scales how strongly the surfaces are tinted; 1 suits most hues. */
  tint?: number
}

// Status colours keep their meaning in every theme: same hues everywhere, with
// lightness fitted to the theme so they stay readable on it.
const STATUS_HUES = { success: 152, info: 245, warning: 70, error: 25 }

function pastel(spec: PastelSpec): ThemeDefinition {
  const h = spec.hue
  const k = spec.tint ?? 1
  const tint = (l: number, c: number) => oklch(l, c * k, h)

  const background = tint(0.95, 0.045)
  const ink = oklch(0.27, 0.055, h)
  const inkSoft = oklch(0.4, 0.07, h)
  // Strong enough to be text on the page and to carry white text itself.
  const strong = (hue: number, c = 0.16, ratio = 4.5) => withContrast({ l: 0.62, c, h: hue }, background, ratio)
  const on = (bg: string) => readableOn(bg, '#ffffff', ink)

  const primary = strong(spec.primaryHue ?? h)
  const secondary = strong(spec.secondaryHue, 0.14)
  const accent = strong(spec.accentHue, 0.13)
  const success = strong(STATUS_HUES.success, 0.14)
  const info = strong(STATUS_HUES.info, 0.14)
  // Amber can't both carry text and be text: deep enough for white it turns
  // brown. So it stays amber with the ink on it, as dark as that allows.
  const warning = withContrast({ l: 0.6, c: 0.15, h: STATUS_HUES.warning }, ink, 4.5)
  const error = strong(STATUS_HUES.error, 0.17)
  const shade = oklch(0.3, 0.07, h)

  return {
    dark: false,
    colors: {
      background,
      'on-background': ink,
      surface: tint(0.978, 0.02),
      'on-surface': ink,
      'surface-bright': tint(0.99, 0.01),
      'on-surface-bright': ink,
      'surface-light': tint(0.93, 0.055),
      'on-surface-light': ink,
      'surface-variant': tint(0.905, 0.065),
      'on-surface-variant': inkSoft,
      nav: tint(0.915, 0.07),
      'on-nav': ink,
      'app-bar': background,
      'on-app-bar': ink,
      primary,
      'on-primary': on(primary),
      secondary,
      'on-secondary': on(secondary),
      accent,
      'on-accent': on(accent),
      success,
      'on-success': on(success),
      info,
      'on-info': on(info),
      warning,
      'on-warning': on(warning),
      error,
      'on-error': on(error),
    },
    variables: {
      'border-color': oklch(0.38, 0.07, h),
      'border-opacity': 0.16,
      'high-emphasis-opacity': 0.92,
      'medium-emphasis-opacity': 0.68,
      'hover-opacity': 0.06,
      'theme-kbd': tint(0.905, 0.065),
      'theme-on-kbd': ink,
      'theme-code': tint(0.93, 0.055),
      'theme-on-code': ink,
      'shadow-key-umbra-opacity': rgba(shade, 0.14),
      'shadow-key-penumbra-opacity': rgba(shade, 0.1),
      'shadow-key-ambient-opacity': rgba(shade, 0.08),
    },
  }
}

function pastelNight(spec: PastelSpec): ThemeDefinition {
  const h = spec.hue
  const k = spec.tint ?? 1
  const tint = (l: number, c: number) => oklch(l, c * k, h)

  const background = tint(0.22, 0.032)
  const ink = oklch(0.95, 0.015, h)
  const deep = oklch(0.24, 0.05, h)
  // Pastel foregrounds: light, soft, and well clear of the page.
  const soft = (hue: number, c = 0.11, ratio = 7) => withContrast({ l: 0.78, c, h: hue }, background, ratio)
  const on = (bg: string) => readableOn(bg, deep, '#ffffff')

  const primary = soft(spec.primaryHue ?? h, 0.12)
  const secondary = soft(spec.secondaryHue)
  const accent = soft(spec.accentHue, 0.1)
  const success = soft(STATUS_HUES.success, 0.11)
  const info = soft(STATUS_HUES.info, 0.1)
  const warning = soft(STATUS_HUES.warning, 0.11)
  const error = soft(STATUS_HUES.error, 0.11)

  return {
    dark: true,
    colors: {
      background,
      'on-background': ink,
      surface: tint(0.27, 0.038),
      'on-surface': ink,
      'surface-bright': tint(0.37, 0.045),
      'on-surface-bright': ink,
      'surface-light': tint(0.32, 0.042),
      'on-surface-light': ink,
      'surface-variant': tint(0.34, 0.048),
      'on-surface-variant': oklch(0.87, 0.03, h),
      nav: tint(0.245, 0.036),
      'on-nav': ink,
      'app-bar': background,
      'on-app-bar': ink,
      primary,
      'on-primary': on(primary),
      secondary,
      'on-secondary': on(secondary),
      accent,
      'on-accent': on(accent),
      success,
      'on-success': on(success),
      info,
      'on-info': on(info),
      warning,
      'on-warning': on(warning),
      error,
      'on-error': on(error),
    },
    variables: {
      'border-color': oklch(0.9, 0.03, h),
      'border-opacity': 0.14,
      'high-emphasis-opacity': 0.95,
      'medium-emphasis-opacity': 0.72,
      'theme-kbd': tint(0.34, 0.048),
      'theme-on-kbd': ink,
      'theme-code': tint(0.32, 0.042),
      'theme-on-code': ink,
      'shadow-key-umbra-opacity': rgba(oklch(0.08, 0.03, h), 0.4),
      'shadow-key-penumbra-opacity': rgba(oklch(0.08, 0.03, h), 0.3),
      'shadow-key-ambient-opacity': rgba(oklch(0.08, 0.03, h), 0.24),
    },
  }
}

const pastelLavender = pastel({ hue: 295, secondaryHue: 355, accentHue: 190 })
const pastelMint = pastel({ hue: 165, secondaryHue: 235, accentHue: 20 })
const pastelPeach = pastel({ hue: 50, primaryHue: 38, secondaryHue: 200, accentHue: 350 })
const pastelSky = pastel({ hue: 240, secondaryHue: 15, accentHue: 165 })
const pastelRose = pastel({ hue: 355, secondaryHue: 300, accentHue: 195 })
const pastelLemon = pastel({ hue: 100, primaryHue: 62, secondaryHue: 150, accentHue: 245, tint: 1.15 })
const pastelLilacNight = pastelNight({ hue: 300, secondaryHue: 240, accentHue: 180 })
const pastelMintNight = pastelNight({ hue: 168, secondaryHue: 235, accentHue: 355 })

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
