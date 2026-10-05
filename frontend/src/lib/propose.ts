import type { ChangeAction, ItemType } from '@/api/types'

/**
 * Context passed to ProposeChangeDialog describing the change being proposed.
 * The dialog asks for the *reason* — once — and submits a change request with
 * this action + payload. What the change is follows from the action and its
 * payload (the server words the description), so it is never asked for.
 */
export interface ProposeContext {
  action: ChangeAction
  itemId?: number | null
  templateId?: number | null
  itemType?: ItemType | null
  payload: Record<string, unknown>
  targetName?: string
  summaryLines?: { label: string; value: string }[]
  /** A reason the user already typed (e.g. the note of a move or a state
   *  change): pre-fills the field so it isn't asked for a second time. */
  reason?: string | null
}
