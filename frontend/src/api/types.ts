// ---------------------------------------------------------------------------
// Lattice API contract types — mirrors docs/CONTRACT.md exactly.
// ---------------------------------------------------------------------------

export type ItemType = 'setup' | 'assembly' | 'card'
/** copied (formerly "unique"), house (formerly "company"), white, factory,
 *  commercial. Only a commercial card holds a quantity. */
export type CardType = 'copied' | 'house' | 'white' | 'factory' | 'commercial'
/** How a card's stock is counted: one row holding a quantity of interchangeable
 *  parts (commercial), or one row per physical unit. */
export type CardTracking = 'quantity' | 'serial'
export type ItemState = 'built' | 'ok' | 'faulty' | 'destroyed'
/** Derived from parent + location (never stored). */
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
  | 'template_create'
  | 'template_update'

/** fixed = white (set on the template, shared by every item);
 *  choice = white with a list (template defines the list, item picks; first = default);
 *  item = grey (filled in when an item is created). */
export type FieldMode = 'fixed' | 'choice' | 'item'
export type FieldType =
  | 'text'
  | 'description'
  | 'string'
  | 'serial_string'
  | 'link'
  | 'enum'
  | 'letter'
  | 'date'
  | 'integer'
  | 'decimal'
  | 'boolean'
  | 'files'
  | 'industry'
  | 'project'
  | 'team'
  | 'managers'
  | 'responsible'
  | 'location'
  | 'parent'
  | 'status'
  | 'quantity'

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
  /** Part of the desiccator group: loose cards here are available stock. */
  is_desiccator: boolean
  item_count: number
}

export interface LocationBody {
  name?: string
  building?: string | null
  room?: string | null
  x?: number
  y?: number
  notes?: string | null
  is_desiccator?: boolean
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

// ---- Templates --------------------------------------------------------------
export interface DocumentOut {
  id: number
  name: string
  doc_type: string | null
  url: string | null
  is_file: boolean
  original_filename: string | null
  content_type: string | null
  size_bytes: number | null
  field_id: number | null
  created_at: string | null
}

export interface FieldConfig {
  /** The field's name in other UI languages ({ he: '…', en: '…' }). */
  labels?: Record<string, string>
  /** A list field's values (ids for reference types) / an enum's strings. */
  options?: unknown[]
  /** "XX-#####": # is a digit the user types, the rest is filled in. */
  pattern?: string
  /** Description: minimum non-blank characters. */
  min_length?: number
}

export interface TemplateFieldIn {
  id?: number | null
  key?: string | null
  label: string
  field_type: FieldType
  mode: FieldMode
  required: boolean
  config: FieldConfig
  fixed_value?: unknown
  /** Creating only (duplicating): copy the files of this template field. */
  copy_files_from?: number | null
}

export interface TemplateFieldOut {
  id: number
  key: string
  label: string
  field_type: FieldType
  mode: FieldMode
  required: boolean
  position: number
  config: FieldConfig
  fixed_value: unknown
  fixed_display: unknown
  /** Labels of a list field's options, aligned with config.options. */
  options_display: string[]
  files: DocumentOut[]
}

export interface TemplateBrief {
  id: number
  type: ItemType
  name: string
  card_type: CardType | null
  serial_prefix: string
}

/** Units per state; `total` excludes destroyed ones. */
export interface TemplateCounts {
  built: number
  ok: number
  faulty: number
  total: number
  destroyed: number
}

export interface TemplateSummary extends TemplateBrief {
  tracking: CardTracking | null
  description: string | null
  counts: TemplateCounts
  child_template_ids: number[]
  parent_template_ids: number[]
  field_count: number
  updated_at: string | null
}

/** One allowed child template and how many units of it one item holds. */
export interface TemplateChildIn {
  template_id: number
  min_count: number
  /** null = no upper limit. */
  max_count: number | null
}

export interface TemplateChildOut {
  template: TemplateBrief
  min_count: number
  max_count: number | null
}

export interface TemplateOut extends TemplateSummary {
  fields: TemplateFieldOut[]
  children: TemplateChildOut[]
  child_templates: TemplateBrief[]
  parent_templates: TemplateBrief[]
  next_serial: string | null
  created_at: string | null
}

export interface TemplateCreate {
  type: ItemType
  name: string
  card_type?: CardType | null
  serial_prefix: string
  description?: string | null
  fields: TemplateFieldIn[]
  children: TemplateChildIn[]
  /** Set when the template is a duplicate of another. */
  source_template_id?: number | null
}

export type TemplateUpdate = Partial<Omit<TemplateCreate, 'type' | 'source_template_id'>>

// ---- Field groups ---------------------------------------------------------
export interface FieldGroupField {
  key: string
  label: string
  field_type: FieldType
  mode: FieldMode
  required: boolean
  position: number
  config: FieldConfig
  fixed_value: unknown
  fixed_display: unknown
  options_display: string[]
}

export interface FieldGroupOut {
  id: number
  name: string
  description: string | null
  fields: FieldGroupField[]
  created_at: string | null
  updated_at: string | null
}

export interface FieldGroupIn {
  name: string
  description?: string | null
  fields: TemplateFieldIn[]
}

// ---- Items ----------------------------------------------------------------
export interface CatalogRef {
  id: number
  value: string
}

export interface ItemBrief {
  id: number
  type: ItemType
  template_id: number
  name: string
  serial: string
  state: ItemState
  card_type?: CardType | null
  location_id?: number | null
}

export interface ItemListOut {
  id: number
  type: ItemType
  template_id: number
  name: string
  serial: string
  state: ItemState
  card_type: CardType | null
  quantity: number
  storage_status: StorageStatus | null
  parent_id: number | null
  parent_label: string | null
  location_id: number | null
  location_name: string | null
  industry: string | null
  project: string | null
  team: string | null
  children_count: number
  /** Units still missing to reach the template's minimum contents. */
  missing_children: number
  manager_names: string[]
  updated_at: string
}

export interface ItemField {
  field_id: number
  key: string
  label: string
  field_type: FieldType
  mode: FieldMode
  required: boolean
  config: FieldConfig
  value: unknown
  /** Human-readable value: names for ids, documents for files. */
  display: unknown
  missing: boolean
}

export interface StateHistoryEntry {
  id: number
  state: ItemState
  note: string | null
  changed_by: number | null
  changed_by_name: string | null
  changed_at: string
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
  template: TemplateBrief
  name: string
  serial: string
  state: ItemState
  card_type: CardType | null
  tracking: CardTracking | null
  quantity: number
  storage_status: StorageStatus | null
  parent_id: number | null
  location_id: number | null
  location: LocationOut | null
  parent: ItemBrief | null
  children: ItemBrief[]
  industry: CatalogRef | null
  project: CatalogRef | null
  team: CatalogRef | null
  responsible: UserBrief | null
  managers: UserBrief[]
  fields: ItemField[]
  state_history: StateHistoryEntry[]
  documents: DocumentOut[]
  extra_items: ExtraItemOut[]
  child_templates: TemplateBrief[]
  /** Templates whose items this one may be placed inside. */
  parent_templates: TemplateBrief[]
  /** Per allowed child template: what is inside against the template's limits. */
  composition: CompositionRow[]
  is_complete: boolean
  created_at: string
  updated_at: string
}

export interface CompositionRow {
  template: TemplateBrief
  min_count: number
  max_count: number | null
  count: number
  missing: number
  is_full: boolean
}

export interface ItemCreate {
  template_id: number
  /** {field key: value} for the template's per-item and list fields. */
  values: Record<string, unknown>
  /** Leave empty to get the template's next serial. */
  serial?: string | null
  child_ids?: number[]
  /** An existing item to place the new one inside. */
  parent_id?: number | null
}

export interface ItemUpdate {
  /** Only the fields being changed. */
  values?: Record<string, unknown>
  serial?: string | null
}

export interface ItemQuery {
  type?: ItemType
  template_id?: number
  state?: ItemState
  card_type?: CardType
  storage_status?: StorageStatus
  location_id?: number
  parent_id?: number
  unassigned?: boolean
  include_destroyed?: boolean
  /** Items whose template may be placed inside this template. */
  child_of_template?: number
  /** Items whose template may contain this template. */
  parent_of_template?: number
  search?: string
  limit?: number
  offset?: number
}

// ---- Catalog (admin vocabularies) -----------------------------------------
export type CatalogCategory = 'project' | 'industry' | 'team'

export interface CatalogOption {
  id: number
  category: CatalogCategory
  value: string
  description: string | null
  active: boolean
  sort_order: number
  usage_count: number
  /** Values of other categories this one is linked to (two-way). */
  linked_ids: number[]
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
  kind: 'item' | 'template' | 'location' | 'user'
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
  templates: SearchHit[]
  locations: SearchHit[]
  users: SearchHit[]
}

// ---- Change requests ------------------------------------------------------
export interface ChangeRequestCreate {
  action: ChangeAction
  item_id?: number | null
  template_id?: number | null
  item_type?: ItemType | null
  payload: Record<string, unknown>
  /** What changes — generated from the action when left out. */
  description?: string | null
  reason: string
}

export interface ChangeRequestOut {
  id: number
  action: ChangeAction
  item_id: number | null
  template_id: number | null
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
  cards_available: number
  faulty_items: number
  pending_change_requests: number
  low_stock_alerts: number
  templates: number
}

/** Stock of one card template. */
export interface InventoryGroup {
  template_id: number
  name: string
  card_type: CardType
  tracking: CardTracking | null
  serial_prefix: string
  total: number
  /** Built/ok at a desiccator location — what thresholds watch. */
  available: number
  /** At a desiccator location, loose or assembled. */
  desiccator: number
  in_use: number
  /** Inside an item outside the desiccator. */
  assembled: number
  /** The part of `desiccator` sitting inside assemblies. */
  assembled_in_desiccator: number
  faulty: number
  records: number
  available_serials: string[]
  min_quantity: number | null
  is_low: boolean
}

export interface ThresholdOut {
  id: number
  template_id: number
  name: string
  card_type: CardType | null
  tracking: CardTracking | null
  min_quantity: number
  editor_email: string | null
  current_quantity: number
  is_low: boolean
}

export interface ThresholdCreate {
  template_id: number
  min_quantity: number
  editor_email?: string | null
}

// ---- Graph ----------------------------------------------------------------
export interface GraphNode {
  id: number
  label: string
  type: ItemType
  state: ItemState | null
  card_type: CardType | null
  serial: string | null
  template_id: number | null
  /** Template graph: live units made from the template. */
  count: number | null
}

export interface GraphEdge {
  source: number
  target: number
}

export interface GraphOut {
  nodes: GraphNode[]
  edges: GraphEdge[]
  roots: number[]
}

// ---- Audit ----------------------------------------------------------------
export type AuditPeriod = 'day' | 'week' | 'month' | 'half_year' | 'year' | 'all'

export interface AuditOut {
  id: number
  item_id: number | null
  template_id: number | null
  item_name: string | null
  action: string
  summary: string
  details: Record<string, unknown>
  user_id: number | null
  user_name: string | null
  created_at: string
}

export interface AuditQuery {
  item_id?: number
  template_id?: number
  period?: AuditPeriod
  mine?: boolean
  action?: string
  search?: string
  limit?: number
}

// ---- Import / Export ------------------------------------------------------
export interface ImportCellError {
  sheet: string
  /** A1 reference, e.g. "C5" (null for sheet-level problems). */
  cell: string | null
  row: number | null
  column: string | null
  error: string
}

export interface ImportResult {
  created: number
  by_template: Record<string, number>
  errors: ImportCellError[]
}

// ---- Notifications --------------------------------------------------------
export type NotificationStatus = 'all' | 'unread' | 'read'

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

export interface NotificationCounts {
  total: number
  unread: number
  read: number
}

export interface LowStockComponent {
  threshold_id: number
  template_id?: number | null
  /** Older alerts pointed at a card; newer ones at the card's template. */
  item_id?: number | null
  link: string
  name: string
  card_type: CardType | null
  tracking: CardTracking | null
  version?: string | null
  current_quantity: number
  min_quantity: number
  /** How many units to add to climb back above the minimum. */
  shortfall: number
}

export interface NotificationPayload {
  components?: LowStockComponent[]
  [key: string]: unknown
}
