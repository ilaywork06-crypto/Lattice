// ---------------------------------------------------------------------------
// Lattice API contract types — mirrors docs/CONTRACT.md exactly.
// ---------------------------------------------------------------------------

export type ItemType = 'setup' | 'assembly' | 'card'
export type CardType = 'commercial' | 'company' | 'unique'
/** How a card's stock is counted: one row holding a quantity of interchangeable
 *  parts (commercial), or one row per physical unit keyed by serial. */
export type CardTracking = 'quantity' | 'serial'
export type ItemState = 'production' | 'built' | 'used' | 'working' | 'faulty'
export type StorageStatus = 'assembled' | 'in_use' | 'desiccator'
export type UserRole = 'viewer' | 'editor' | 'manager'
export type ChangeStatus = 'pending' | 'approved' | 'rejected'
export type ChangeAction =
  | 'create'
  | 'update'
  | 'delete'
  | 'move'
  | 'link'
  | 'unlink'
  | 'state_change'

// ---- Auth -----------------------------------------------------------------
export interface LoginResponse {
  access_token: string
  token_type: string
  role: UserRole
  full_name: string
  user_id: number
}

export interface UserBrief {
  id: number
  full_name: string
  email: string
  role: UserRole
}

export interface User extends UserBrief {
  is_active: boolean
  created_at?: string
  /** Offered as a shortcut on the sign-in screen. */
  login_hint_visible: boolean
  /** Whether a password is published with that shortcut — never the value. */
  has_login_hint_password: boolean
}

/** A sign-in shortcut, served unauthenticated to the login page. `password` is
 *  filled in only where a manager explicitly published one. */
export interface LoginHint {
  full_name: string
  email: string
  role: UserRole
  password: string | null
}

// ---- Locations ------------------------------------------------------------
export interface LocationOut {
  id: number
  name: string
  building: string | null
  room: string | null
  x: number
  y: number
  notes: string | null
  item_count: number
}

export interface LocationBrief {
  id: number
  name: string
  building?: string | null
  room?: string | null
}

// ---- Map buildings (editable floor-plan background) ------------------------
export interface MapBuilding {
  id: number
  name: string
  x: number
  y: number
  width: number
  height: number
  color: string | null
  notes: string | null
  sort_order: number
}

export interface MapBuildingCreate {
  name: string
  x: number
  y: number
  width: number
  height: number
  color?: string | null
  notes?: string | null
  sort_order?: number
}

export type MapBuildingUpdate = Partial<MapBuildingCreate>

// ---- Items ----------------------------------------------------------------
export interface ItemBrief {
  id: number
  type: ItemType
  name: string
  state: ItemState
  card_type?: CardType | null
}

export interface ItemListOut {
  id: number
  type: ItemType
  name: string
  industry: string | null
  project: string | null
  team: string | null
  state: ItemState
  card_type: CardType | null
  version: string | null
  serial: string | null
  quantity: number
  storage_status: StorageStatus | null
  parent_id: number | null
  location_id: number | null
  location_name: string | null
  children_count: number
  is_template: boolean
  manager_names: string[]
  updated_at: string
}

export interface StateHistoryEntry {
  id?: number
  state: ItemState
  note: string | null
  changed_by?: string | null
  created_at: string
}

export interface DocumentOut {
  id: number
  name: string
  url: string | null
  doc_type: string | null
}

export interface ExtraItemOut {
  id: number
  name: string
  company_part_number: string | null
  serial: string | null
  signed_by: string | null
}

export interface ItemOut {
  id: number
  type: ItemType
  is_template: boolean
  name: string
  industry: string | null
  project: string | null
  team: string | null
  state: ItemState
  description: string | null
  dmz: string | null
  card_type: CardType | null
  responsible: string | null
  lead: string | null
  production_date: string | null
  version: string | null
  serial: string | null
  /** Units on this row. Always 1 for serial-tracked cards and non-cards. */
  quantity: number
  storage_status: StorageStatus | null
  parent_id: number | null
  location_id: number | null
  updated_at: string
  created_at?: string
  location: LocationBrief | null
  parent: ItemBrief | null
  children: ItemBrief[]
  managers: UserBrief[]
  state_history: StateHistoryEntry[]
  documents: DocumentOut[]
  extra_items: ExtraItemOut[]
}

export interface ItemCreate {
  type: ItemType
  name: string
  industry?: string | null
  project?: string | null
  team?: string | null
  state?: ItemState
  description?: string | null
  dmz?: string | null
  location_id?: number | null
  parent_id?: number | null
  is_template?: boolean
  card_type?: CardType | null
  responsible?: string | null
  lead?: string | null
  production_date?: string | null
  version?: string | null
  serial?: string | null
  quantity?: number
  storage_status?: StorageStatus | null
  manager_ids?: number[]
  child_ids?: number[]
}

export type ItemUpdate = Partial<Omit<ItemCreate, 'type'>> & {
  /** Explains a state transition. Required when moving into or out of `faulty`;
   *  update-only, since creating an item sets an initial state, not a transition. */
  state_note?: string | null
}

export interface ItemQuery {
  type?: ItemType
  state?: ItemState
  card_type?: CardType
  storage_status?: StorageStatus
  project?: string
  industry?: string
  location_id?: number
  unassigned?: boolean
  templates?: boolean
  search?: string
  limit?: number
  offset?: number
}

// ---- Catalog (admin vocabularies) -----------------------------------------
export type CatalogCategory = 'project' | 'industry'

export interface CatalogOption {
  id: number
  category: CatalogCategory
  value: string
  description: string | null
  active: boolean
  sort_order: number
  usage_count: number
}

export interface CatalogOptionCreate {
  category: CatalogCategory
  value: string
  description?: string | null
  active?: boolean
  sort_order?: number
}

// ---- Bulk operations ------------------------------------------------------
export type BulkAction = 'move' | 'state_change' | 'delete' | 'link' | 'unlink'

export interface BulkRequest {
  action: BulkAction
  item_ids: number[]
  location_id?: number | null
  parent_id?: number | null
  state?: ItemState | null
  note?: string | null
}

export interface BulkResult {
  processed: number
  failed: number
  errors: string[]
}

// ---- Global search --------------------------------------------------------
export interface SearchHit {
  kind: 'item' | 'location' | 'user' | 'change_request'
  id: number
  title: string
  subtitle: string | null
  badge: string | null
  state: ItemState | null
  link: string
}

export interface SearchResults {
  query: string
  total: number
  items: SearchHit[]
  locations: SearchHit[]
  users: SearchHit[]
}

// ---- Change requests ------------------------------------------------------
export interface ChangeRequestCreate {
  action: ChangeAction
  item_id?: number | null
  item_type?: ItemType | null
  payload: Record<string, unknown>
  description: string
  reason: string
}

export interface ChangeRequestOut {
  id: number
  action: ChangeAction
  item_id: number | null
  item_type: ItemType | null
  item_name: string | null
  payload: Record<string, unknown>
  description: string
  reason: string
  status: ChangeStatus
  proposed_by: number
  reviewed_by: number | null
  review_note: string | null
  created_at: string
  reviewed_at: string | null
  proposer: UserBrief | null
  reviewer: UserBrief | null
}

// ---- Inventory ------------------------------------------------------------
export interface InventorySummary {
  setups: number
  assemblies: number
  cards: number
  cards_in_use: number
  cards_desiccator: number
  faulty_items: number
  pending_change_requests: number
  low_stock_alerts: number
}

export interface InventoryGroup {
  card_type: CardType
  /** How `total` was arrived at — summed quantities, or one row per unit. */
  tracking: CardTracking | null
  name: string
  version: string | null
  production_date: string | null
  total: number
  in_use: number
  desiccator: number
  assembled: number
  /** How many item rows add up to `total`. */
  records: number
  serials: string[]
}

export interface ThresholdOut {
  id: number
  card_type: CardType
  tracking: CardTracking | null
  name: string
  version: string | null
  min_quantity: number
  editor_email: string | null
  current_quantity: number
  is_low: boolean
}

export interface ThresholdCreate {
  card_type: CardType
  name: string
  version?: string | null
  min_quantity: number
}

// ---- Graph ----------------------------------------------------------------
export interface GraphNode {
  id: number
  label: string
  type: ItemType
  state: ItemState
  card_type: CardType | null
}

export interface GraphEdge {
  source: number
  target: number
}

export interface GraphOut {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

// ---- Audit ----------------------------------------------------------------
export interface AuditOut {
  id: number
  item_id: number | null
  item_name: string | null
  action: string
  summary: string
  details: string | null
  user_id: number | null
  user_name: string | null
  created_at: string
}

// ---- Import / Export ------------------------------------------------------
export interface ImportResult {
  created: number
  errors: { row: number; error: string }[]
}

// ---- Notifications --------------------------------------------------------
export interface NotificationItem {
  id: number
  type: string
  title: string
  body: string | null
  /** Structured context from the source event. Low-stock alerts carry
   *  `{ components: LowStockComponent[] }` so the list renders as a table. */
  payload: NotificationPayload | null
  link: string | null
  read: boolean
  created_at: string
}

export interface LowStockComponent {
  threshold_id: number
  name: string
  card_type: CardType
  tracking: CardTracking | null
  version: string | null
  current_quantity: number
  min_quantity: number
  /** How many units to add to climb back above the minimum. */
  shortfall: number
}

export interface NotificationPayload {
  components?: LowStockComponent[]
  [key: string]: unknown
}
