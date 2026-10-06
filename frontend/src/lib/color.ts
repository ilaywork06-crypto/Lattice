// Small colour toolkit for building themes.
//
// Palettes are specified in OKLCH — lightness, chroma, hue — because its
// lightness is perceptual: a lavender and a lemon at the same L really do look
// equally light, so one set of lightness steps serves every hue. Readability is
// then checked with the WCAG contrast ratio rather than assumed.

/** An OKLCH colour: L in 0..1, C ≥ 0 (≈0.37 is the most sRGB reaches), h in degrees. */
export interface Oklch {
  l: number
  c: number
  h: number
}

type Rgb = [number, number, number]

/** OKLCH → linear-light sRGB (components may fall outside 0..1). */
function oklchToLinear({ l, c, h }: Oklch): Rgb {
  const rad = (h * Math.PI) / 180
  const a = c * Math.cos(rad)
  const b = c * Math.sin(rad)
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3
  return [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ]
}

const inGamut = (rgb: Rgb) => rgb.every((v) => v >= -1e-4 && v <= 1 + 1e-4)

/** The colour itself if sRGB can show it, otherwise the same L and h with the
 *  most chroma that fits (saturated yellows and blues run out early). */
function toGamut(color: Oklch): Rgb {
  const rgb = oklchToLinear(color)
  if (inGamut(rgb)) return rgb
  let lo = 0
  let hi = color.c
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2
    if (inGamut(oklchToLinear({ ...color, c: mid }))) lo = mid
    else hi = mid
  }
  return oklchToLinear({ ...color, c: lo })
}

const encode = (v: number) => {
  const x = Math.min(1, Math.max(0, v))
  return x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055
}
const decode = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)

export function oklch(l: number, c: number, h: number): string {
  return (
    '#' +
    toGamut({ l, c, h })
      .map((v) => Math.round(encode(v) * 255).toString(16).padStart(2, '0'))
      .join('')
  )
}

function hexToLinear(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => decode(v / 255)) as Rgb
}

/** WCAG relative luminance of a #rrggbb colour. */
export function luminance(hex: string): number {
  const [r, g, b] = hexToLinear(hex)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** WCAG contrast ratio between two #rrggbb colours (1..21). */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * The colour at `start`, moved along lightness — darker when `against` is
 * light, lighter when it is dark — until it reaches `ratio` contrast with it.
 * Hue and chroma are kept, so the colour stays recognisably itself.
 */
export function withContrast(start: Oklch, against: string, ratio: number): string {
  const step = luminance(against) > 0.18 ? -0.01 : 0.01
  let { l } = start
  let hex = oklch(l, start.c, start.h)
  while (contrast(hex, against) < ratio && l > 0.05 && l < 0.98) {
    l += step
    hex = oklch(l, start.c, start.h)
  }
  return hex
}

/** Whichever of the candidates reads best on `background`. */
export function readableOn(background: string, ...candidates: string[]): string {
  return candidates.reduce((best, c) => (contrast(c, background) > contrast(best, background) ? c : best))
}

/** `rgba(…)` of a #rrggbb colour — for CSS values Vuetify passes through as-is. */
export function rgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}
