import type {
  CardType,
  ChangeAction,
  ChangeStatus,
  ItemState,
  ItemType,
  StorageStatus,
  UserRole,
} from '@/api/types'
import { i18n } from '@/i18n'

// A translated label map: reading `MAP[key]` returns the localized string for
// `enums.<ns>.<key>`. Because it calls i18n's `t()` (which reads the reactive
// locale), any template/computed that indexes it re-renders on locale change —
// so all existing `STATE_LABELS[x]` call sites localize with zero changes.
function labelMap<K extends string>(ns: string): Record<K, string> {
  return new Proxy({} as Record<K, string>, {
    get: (_t, key: string) => i18n.global.t(`enums.${ns}.${key}`),
  })
}

// State → Vuetify color mapping (working=green, faulty=red, built=blue,
// production=amber, used=grey) per the spec.
export const STATE_COLORS: Record<ItemState, string> = {
  working: 'success',
  faulty: 'error',
  built: 'info',
  production: 'amber-darken-2',
  used: 'grey',
}

export const STATE_LABELS = labelMap<ItemState>('state')

export const ITEM_STATES: ItemState[] = ['production', 'built', 'used', 'working', 'faulty']

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

export const ITEM_TYPES: ItemType[] = ['setup', 'assembly', 'card']

export const CARD_TYPES: CardType[] = ['commercial', 'company', 'unique']

export const CARD_TYPE_LABELS = labelMap<CardType>('cardType')

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
}

// Reading i18n's reactive locale keeps date formatting in sync with the
// language choice (and makes these reactive inside templates/computeds).
function intlLocale(): string {
  return i18n.global.locale.value === 'he' ? 'he-IL' : 'en-GB'
}

export function formatDate(value?: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
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
