import type { ChangeAction, ItemType } from '@/api/types'

/**
 * Context passed to ProposeChangeDialog describing the change an editor is
 * proposing. The dialog collects `description` + `reason` and submits a
 * change-request with this action + payload.
 */
export interface ProposeContext {
  action: ChangeAction
  itemId?: number | null
  itemType?: ItemType | null
  payload: Record<string, unknown>
  targetName?: string
  summaryLines?: { label: string; value: string }[]
}
