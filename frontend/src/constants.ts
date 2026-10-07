import type {
  CardTracking,
  CardType,
  ChangeAction,
  ChangeStatus,
  FieldConfig,
  FieldMode,
  FieldType,
  ItemState,
  ItemType,
  StorageStatus,
  UserRole,
} from '@/api/types'
import { AVAILABLE_LOCALES, i18n } from '@/i18n'

// A translated label map: reading `MAP[key]` returns the localized string for
// `enums.<ns>.<key>`. Because it calls i18n's `t()` (which reads the reactive
// locale), any template/computed that indexes it re-renders on locale change —
// so all existing `STATE_LABELS[x]` call sites localize with zero changes.
function labelMap<K extends string>(ns: string): Record<K, string> {
  return new Proxy({} as Record<K, string>, {
    get: (_t, key: string) => i18n.global.t(`enums.${ns}.${key}`),
  })
}

// built = blue, ok = green, faulty = red, destroyed = grey.
export const STATE_COLORS: Record<ItemState, string> = {
  built: 'info',
  ok: 'success',
  faulty: 'error',
  destroyed: 'grey-darken-1',
}

export const STATE_LABELS = labelMap<ItemState>('state')

/** An audit action code ("template.update") in the UI language. */
export function auditActionLabel(action: string): string {
  const key = `enums.auditAction.${action.replace(/\./g, '_')}`
  return i18n.global.te(key) ? i18n.global.t(key) : action
}

export const ITEM_STATES: ItemState[] = ['built', 'ok', 'faulty', 'destroyed']
/** The states counted on list pages (destroyed units are history). */
export const ACTIVE_STATES: ItemState[] = ['built', 'ok', 'faulty']

export const TYPE_ICONS: Record<ItemType, string> = {
  setup: 'mdi-server',
  assembly: 'mdi-cpu-64-bit',
  card: 'mdi-memory',
}

export const TYPE_COLORS: Record<ItemType, string> = {
  setup: 'deep-purple',
  assembly: 'teal-darken-1',
  card: 'blue-darken-1',
}

export const TYPE_LABELS = labelMap<ItemType>('type')

// Hierarchy graph palette: fill by type, border by state.
export const GRAPH_TYPE_FILL: Record<ItemType, string> = {
  setup: '#7e6bc4',
  assembly: '#3a9e92',
  card: '#4a8fd9',
}
export const GRAPH_STATE_BORDER: Record<ItemState, string> = {
  built: '#2f80ed',
  ok: '#2e9e5b',
  faulty: '#e5484d',
  destroyed: '#6b6f7b',
}

export const ITEM_TYPES: ItemType[] = ['setup', 'assembly', 'card']

export const CARD_TYPES: CardType[] = ['copied', 'house', 'white', 'factory', 'commercial']

export const CARD_TYPE_LABELS = labelMap<CardType>('cardType')

export const CARD_TYPE_COLORS: Record<CardType, string> = {
  copied: 'deep-orange',
  house: 'indigo',
  white: 'blue-grey',
  factory: 'brown',
  commercial: 'teal',
}

// Mirrors `CARD_TRACKING` in the backend's models.py. Only a commercial card is
// a quantity of interchangeable parts; every other card is one unit per serial.
export const CARD_TRACKING: Record<CardType, CardTracking> = {
  copied: 'serial',
  house: 'serial',
  white: 'serial',
  factory: 'serial',
  commercial: 'quantity',
}

export const TRACKING_LABELS = labelMap<CardTracking>('tracking')

export function isQuantityTracked(cardType?: CardType | null): boolean {
  return !!cardType && CARD_TRACKING[cardType] === 'quantity'
}

export const STORAGE_STATUSES: StorageStatus[] = ['assembled', 'in_use', 'desiccator']

export const STORAGE_LABELS = labelMap<StorageStatus>('storage')

export const STORAGE_COLORS: Record<StorageStatus, string> = {
  assembled: 'indigo',
  in_use: 'green',
  desiccator: 'cyan-darken-2',
}

export const STORAGE_ICONS: Record<StorageStatus, string> = {
  assembled: 'mdi-puzzle',
  in_use: 'mdi-power-plug',
  desiccator: 'mdi-water-off',
}

// ---- Template fields --------------------------------------------------------
export const FIELD_MODES: FieldMode[] = ['fixed', 'choice', 'item']
export const FIELD_MODE_LABELS = labelMap<FieldMode>('fieldMode')
export const FIELD_TYPE_LABELS = labelMap<FieldType>('fieldType')

/**
 * A field's name in the UI language. A field still carrying its type's default
 * name (in any language — "Location", "מיקום") follows the UI language; a
 * name given for this language on the field wins; otherwise its own name.
 */
export function fieldLabel(f: { label: string; field_type: FieldType; config?: FieldConfig | null }): string {
  const locale = String(i18n.global.locale.value)
  const own = f.config?.labels?.[locale]?.trim()
  if (own) return own
  const name = f.label.trim().toLowerCase()
  const isDefault = AVAILABLE_LOCALES.some((l) => {
    const msgs = i18n.global.getLocaleMessage(l.code) as { enums?: { fieldType?: Record<string, string> } }
    return msgs.enums?.fieldType?.[f.field_type]?.toLowerCase() === name
  })
  return isDefault ? FIELD_TYPE_LABELS[f.field_type] : f.label
}

/** Grouped for the "add field" menu. */
export const FIELD_TYPE_GROUPS: { group: string; types: FieldType[] }[] = [
  {
    group: 'text',
    types: ['text', 'description', 'string', 'serial_string', 'link', 'enum', 'letter'],
  },
  { group: 'number', types: ['integer', 'decimal', 'quantity', 'boolean', 'date'] },
  { group: 'catalog', types: ['industry', 'project', 'team'] },
  { group: 'people', types: ['managers', 'responsible'] },
  { group: 'physical', types: ['location', 'parent', 'status'] },
  { group: 'files', types: ['files'] },
]

export const FIELD_TYPE_ICONS: Record<FieldType, string> = {
  text: 'mdi-text',
  description: 'mdi-text-long',
  string: 'mdi-form-textbox',
  serial_string: 'mdi-barcode',
  link: 'mdi-link-variant',
  enum: 'mdi-format-list-bulleted',
  letter: 'mdi-alphabetical-variant',
  date: 'mdi-calendar',
  integer: 'mdi-numeric',
  decimal: 'mdi-decimal',
  quantity: 'mdi-counter',
  boolean: 'mdi-toggle-switch-outline',
  industry: 'mdi-factory',
  project: 'mdi-folder-outline',
  team: 'mdi-account-group-outline',
  managers: 'mdi-account-tie',
  responsible: 'mdi-account-star',
  location: 'mdi-map-marker',
  parent: 'mdi-file-tree',
  status: 'mdi-list-status',
  files: 'mdi-paperclip',
}

/** Types stored as real columns — at most one per template. */
export const SYSTEM_FIELD_TYPES: FieldType[] = [
  'industry', 'project', 'team', 'managers', 'responsible', 'location', 'parent', 'status',
  'quantity',
]
/** Physical state of each unit: per item or a list, never fixed. */
export const PER_UNIT_FIELD_TYPES: FieldType[] = ['location', 'parent', 'status', 'quantity']

export const LETTERS = Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i))

/** "XX-#####": # are typed digits, the rest is filled in automatically. */
export function applyPattern(pattern: string, raw: string): string | null {
  const value = raw.trim()
  const re = new RegExp(
    '^' + [...pattern].map((c) => (c === '#' ? '\\d' : c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))).join('') + '$',
  )
  if (re.test(value)) return value
  const digits = value.replace(/\s/g, '')
  const slots = [...pattern].filter((c) => c === '#').length
  if (!/^\d+$/.test(digits) || digits.length !== slots) return null
  let i = 0
  return [...pattern].map((c) => (c === '#' ? digits[i++] : c)).join('')
}

export const ROLE_LABELS = labelMap<UserRole>('role')

export const ROLE_COLORS: Record<UserRole, string> = {
  viewer: 'blue-grey',
  editor: 'orange-darken-2',
  manager: 'deep-purple',
}

export const CHANGE_STATUS_COLORS: Record<ChangeStatus, string> = {
  pending: 'amber-darken-2',
  approved: 'success',
  rejected: 'error',
}

export const CHANGE_ACTION_LABELS = labelMap<ChangeAction>('changeAction')

export const CHANGE_ACTION_ICONS: Record<ChangeAction, string> = {
  create: 'mdi-plus-circle',
  update: 'mdi-pencil',
  delete: 'mdi-delete',
  move: 'mdi-map-marker-radius',
  link: 'mdi-link-variant',
  unlink: 'mdi-link-variant-off',
  state_change: 'mdi-swap-horizontal',
  template_create: 'mdi-shape-square-plus',
  template_update: 'mdi-shape-outline',
}

// Reading i18n's reactive locale keeps date formatting in sync with the
// language choice (and makes these reactive inside templates/computeds).
function intlLocale(): string {
  return i18n.global.locale.value === 'he' ? 'he-IL' : 'en-GB'
}

export function formatBytes(bytes?: number | null): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** A "YYYY-MM-DD" date is a calendar day, not UTC midnight — read it as local. */
export function parseDay(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null
}

/** A local Date as "YYYY-MM-DD" (what date fields store). */
export function toDay(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function formatDate(value?: string | null): string {
  if (!value) return '—'
  const d = parseDay(value) ?? new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString(intlLocale(), { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString(intlLocale(), {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function timeAgo(value?: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const t = i18n.global.t
  const seconds = Math.floor((Date.now() - d.getTime()) / 1000)
  if (seconds < 60) return t('common.justNow')
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return t('common.minutesAgo', { n: minutes })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return t('common.hoursAgo', { n: hours })
  const days = Math.floor(hours / 24)
  if (days < 30) return t('common.daysAgo', { n: days })
  return formatDate(value)
}
