import { coreApi, notificationApi } from './client'
import type {
  AuditOut,
  AuditPeriod,
  AuditQuery,
  BulkRequest,
  BulkResult,
  CatalogCategory,
  CatalogOption,
  CatalogOptionCreate,
  ChangeRequestCreate,
  ChangeRequestOut,
  ChangeStatus,
  DocumentOut,
  ExtraItemOut,
  GraphOut,
  ImportResult,
  InventoryGroup,
  InventorySummary,
  ItemCreate,
  ItemListOut,
  ItemOut,
  ItemQuery,
  ItemState,
  ItemType,
  ItemUpdate,
  LocationBody,
  LocationOut,
  LoginHint,
  LoginResponse,
  MapBuilding,
  MapBuildingCreate,
  MapBuildingUpdate,
  NotificationCounts,
  NotificationItem,
  NotificationStatus,
  SearchResults,
  FieldGroupIn,
  FieldGroupOut,
  TemplateCreate,
  TemplateOut,
  TemplateSummary,
  TemplateUpdate,
  ThresholdCreate,
  ThresholdOut,
  User,
  UserBrief,
  UserRole,
} from './types'

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export const authApi = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const form = new URLSearchParams()
    form.append('username', email)
    form.append('password', password)
    const { data } = await coreApi.post<LoginResponse>('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return data
  },
  async me(): Promise<User> {
    const { data } = await coreApi.get<User>('/auth/me')
    return data
  },
  /** Sign-in shortcuts a manager published. Unauthenticated — it runs before login. */
  async loginHints(): Promise<LoginHint[]> {
    const { data } = await coreApi.get<LoginHint[]>('/auth/login-hints')
    return data
  },
}

// ---------------------------------------------------------------------------
// Items
// ---------------------------------------------------------------------------
export const itemsApi = {
  async list(query: ItemQuery = {}): Promise<ItemListOut[]> {
    const { data } = await coreApi.get<ItemListOut[]>('/items', { params: query })
    return data
  },
  async get(id: number): Promise<ItemOut> {
    const { data } = await coreApi.get<ItemOut>(`/items/${id}`)
    return data
  },
  async create(body: ItemCreate): Promise<ItemOut> {
    const { data } = await coreApi.post<ItemOut>('/items', body)
    return data
  },
  async update(id: number, body: ItemUpdate): Promise<ItemOut> {
    const { data } = await coreApi.patch<ItemOut>(`/items/${id}`, body)
    return data
  },
  async remove(id: number): Promise<void> {
    await coreApi.delete(`/items/${id}`)
  },
  async move(id: number, location_id: number, note?: string): Promise<ItemOut> {
    const { data } = await coreApi.post<ItemOut>(`/items/${id}/move`, { location_id, note })
    return data
  },
  async link(id: number, parent_id: number): Promise<ItemOut> {
    const { data } = await coreApi.post<ItemOut>(`/items/${id}/link`, { parent_id })
    return data
  },
  /** `location_id`: where the item now is (defaults to its container's). */
  async unlink(id: number, location_id?: number | null): Promise<ItemOut> {
    const { data } = await coreApi.post<ItemOut>(`/items/${id}/unlink`, {
      location_id: location_id ?? null,
    })
    return data
  },
  /** Replace a container's contents. `child_ids` is the result, not a delta. */
  async setChildren(id: number, child_ids: number[]): Promise<ItemOut> {
    const { data } = await coreApi.put<ItemOut>(`/items/${id}/children`, { child_ids })
    return data
  },
  async changeState(id: number, state: ItemState, note?: string): Promise<ItemOut> {
    const { data } = await coreApi.post<ItemOut>(`/items/${id}/state`, { state, note })
    return data
  },
  /** Attach an uploaded file or a link to an item. */
  async addDocument(
    id: number,
    body: { file?: File | null; name?: string; url?: string; doc_type?: string },
  ): Promise<DocumentOut> {
    const form = new FormData()
    if (body.file) form.append('file', body.file)
    if (body.name) form.append('name', body.name)
    if (body.url) form.append('url', body.url)
    if (body.doc_type) form.append('doc_type', body.doc_type)
    const { data } = await coreApi.post<DocumentOut>(`/items/${id}/documents`, form)
    return data
  },
  async removeDocument(id: number, docId: number): Promise<void> {
    await coreApi.delete(`/items/${id}/documents/${docId}`)
  },
  async addExtra(
    id: number,
    body: { name: string; company_part_number?: string; serial?: string; signed_by?: string },
  ): Promise<ExtraItemOut> {
    const { data } = await coreApi.post<ExtraItemOut>(`/items/${id}/extras`, body)
    return data
  },
  async removeExtra(id: number, extraId: number): Promise<void> {
    await coreApi.delete(`/items/${id}/extras/${extraId}`)
  },
  async bulk(body: BulkRequest): Promise<BulkResult> {
    const { data } = await coreApi.post<BulkResult>('/items/bulk', body)
    return data
  },
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------
export const fieldGroupsApi = {
  async list(search?: string): Promise<FieldGroupOut[]> {
    const { data } = await coreApi.get<FieldGroupOut[]>('/field-groups', {
      params: search ? { search } : {},
    })
    return data
  },
  async create(body: FieldGroupIn): Promise<FieldGroupOut> {
    const { data } = await coreApi.post<FieldGroupOut>('/field-groups', body)
    return data
  },
  async update(id: number, body: Partial<FieldGroupIn>): Promise<FieldGroupOut> {
    const { data } = await coreApi.patch<FieldGroupOut>(`/field-groups/${id}`, body)
    return data
  },
  async remove(id: number): Promise<void> {
    await coreApi.delete(`/field-groups/${id}`)
  },
}

export const templatesApi = {
  async list(params: { type?: ItemType; search?: string } = {}): Promise<TemplateSummary[]> {
    const { data } = await coreApi.get<TemplateSummary[]>('/templates', { params })
    return data
  },
  async get(id: number): Promise<TemplateOut> {
    const { data } = await coreApi.get<TemplateOut>(`/templates/${id}`)
    return data
  },
  async create(body: TemplateCreate): Promise<TemplateOut> {
    const { data } = await coreApi.post<TemplateOut>('/templates', body)
    return data
  },
  async update(id: number, body: TemplateUpdate): Promise<TemplateOut> {
    const { data } = await coreApi.patch<TemplateOut>(`/templates/${id}`, body)
    return data
  },
  async remove(id: number): Promise<void> {
    await coreApi.delete(`/templates/${id}`)
  },
  /** Files shared by every item (a files field set on the template). */
  async uploadFieldFile(id: number, fieldId: number, file: File): Promise<DocumentOut> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await coreApi.post<DocumentOut>(
      `/templates/${id}/fields/${fieldId}/files`,
      form,
    )
    return data
  },
  async removeFile(id: number, docId: number): Promise<void> {
    await coreApi.delete(`/templates/${id}/files/${docId}`)
  },
}

// ---------------------------------------------------------------------------
// Documents (uploads)
// ---------------------------------------------------------------------------
export const documentsApi = {
  /** Upload a file before the item it belongs to exists; its id then goes
   *  into a files field's value. */
  async stage(file: File): Promise<DocumentOut> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await coreApi.post<DocumentOut>('/uploads', form)
    return data
  },
  async download(id: number): Promise<Blob> {
    const { data } = await coreApi.get(`/documents/${id}/download`, { responseType: 'blob' })
    return data as Blob
  },
}

// ---------------------------------------------------------------------------
// Catalog (admin-managed project / industry vocabularies)
// ---------------------------------------------------------------------------
export const catalogApi = {
  async list(category?: CatalogCategory, activeOnly = false): Promise<CatalogOption[]> {
    const { data } = await coreApi.get<CatalogOption[]>('/catalog', {
      params: { ...(category ? { category } : {}), active_only: activeOnly },
    })
    return data
  },
  async create(body: CatalogOptionCreate): Promise<CatalogOption> {
    const { data } = await coreApi.post<CatalogOption>('/catalog', body)
    return data
  },
  async update(id: number, body: Partial<CatalogOptionCreate>): Promise<CatalogOption> {
    const { data } = await coreApi.patch<CatalogOption>(`/catalog/${id}`, body)
    return data
  },
  /** Set one value's links to another category (two-way). */
  async setLinks(id: number, category: CatalogCategory, optionIds: number[]): Promise<CatalogOption> {
    const { data } = await coreApi.put<CatalogOption>(`/catalog/${id}/links`, {
      category,
      option_ids: optionIds,
    })
    return data
  },
  async remove(id: number): Promise<void> {
    await coreApi.delete(`/catalog/${id}`)
  },
}

// ---------------------------------------------------------------------------
// Global search
// ---------------------------------------------------------------------------
export const searchApi = {
  async query(q: string): Promise<SearchResults> {
    const { data } = await coreApi.get<SearchResults>('/search', { params: { q } })
    return data
  },
}

// ---------------------------------------------------------------------------
// Change requests
// ---------------------------------------------------------------------------
export const changeRequestsApi = {
  async list(params: { status?: ChangeStatus; mine?: boolean } = {}): Promise<ChangeRequestOut[]> {
    const { data } = await coreApi.get<ChangeRequestOut[]>('/change-requests', { params })
    return data
  },
  async get(id: number): Promise<ChangeRequestOut> {
    const { data } = await coreApi.get<ChangeRequestOut>(`/change-requests/${id}`)
    return data
  },
  async create(body: ChangeRequestCreate): Promise<ChangeRequestOut> {
    const { data } = await coreApi.post<ChangeRequestOut>('/change-requests', body)
    return data
  },
  async approve(id: number, note?: string): Promise<ChangeRequestOut> {
    const { data } = await coreApi.post<ChangeRequestOut>(`/change-requests/${id}/approve`, { note })
    return data
  },
  async reject(id: number, note?: string): Promise<ChangeRequestOut> {
    const { data } = await coreApi.post<ChangeRequestOut>(`/change-requests/${id}/reject`, { note })
    return data
  },
}

// ---------------------------------------------------------------------------
// Inventory
// ---------------------------------------------------------------------------
export const inventoryApi = {
  async summary(): Promise<InventorySummary> {
    const { data } = await coreApi.get<InventorySummary>('/inventory/summary')
    return data
  },
  async cards(cardType?: string): Promise<InventoryGroup[]> {
    const { data } = await coreApi.get<InventoryGroup[]>('/inventory/cards', {
      params: cardType ? { card_type: cardType } : {},
    })
    return data
  },
  async desiccator(cardType?: string): Promise<InventoryGroup[]> {
    const { data } = await coreApi.get<InventoryGroup[]>('/inventory/desiccator', {
      params: cardType ? { card_type: cardType } : {},
    })
    return data
  },
  async thresholds(): Promise<ThresholdOut[]> {
    const { data } = await coreApi.get<ThresholdOut[]>('/inventory/thresholds')
    return data
  },
  async lowStock(): Promise<ThresholdOut[]> {
    const { data } = await coreApi.get<ThresholdOut[]>('/inventory/low-stock')
    return data
  },
  async createThreshold(body: ThresholdCreate): Promise<ThresholdOut> {
    const { data } = await coreApi.post<ThresholdOut>('/inventory/thresholds', body)
    return data
  },
  async removeThreshold(id: number): Promise<void> {
    await coreApi.delete(`/inventory/thresholds/${id}`)
  },
}

// ---------------------------------------------------------------------------
// Locations
// ---------------------------------------------------------------------------
export const locationsApi = {
  async list(): Promise<LocationOut[]> {
    const { data } = await coreApi.get<LocationOut[]>('/locations')
    return data
  },
  async create(body: LocationBody): Promise<LocationOut> {
    const { data } = await coreApi.post<LocationOut>('/locations', body)
    return data
  },
  async update(id: number, body: LocationBody): Promise<LocationOut> {
    const { data } = await coreApi.patch<LocationOut>(`/locations/${id}`, body)
    return data
  },
  async remove(id: number): Promise<void> {
    await coreApi.delete(`/locations/${id}`)
  },
  /** Define the desiccator: the full set of locations that belong to it. */
  async setDesiccator(locationIds: number[]): Promise<LocationOut[]> {
    const { data } = await coreApi.put<LocationOut[]>('/locations/desiccator', {
      location_ids: locationIds,
    })
    return data
  },
}

// ---------------------------------------------------------------------------
// Map buildings (editable floor-plan background)
// ---------------------------------------------------------------------------
export const mapApi = {
  async buildings(): Promise<MapBuilding[]> {
    const { data } = await coreApi.get<MapBuilding[]>('/map/buildings')
    return data
  },
  async createBuilding(body: MapBuildingCreate): Promise<MapBuilding> {
    const { data } = await coreApi.post<MapBuilding>('/map/buildings', body)
    return data
  },
  async updateBuilding(id: number, body: MapBuildingUpdate): Promise<MapBuilding> {
    const { data } = await coreApi.patch<MapBuilding>(`/map/buildings/${id}`, body)
    return data
  },
  async removeBuilding(id: number): Promise<void> {
    await coreApi.delete(`/map/buildings/${id}`)
  },
}

// ---------------------------------------------------------------------------
// Graph
// ---------------------------------------------------------------------------
export const graphApi = {
  /** One item's tree (with `ancestors`, the path up to the top as well). */
  async item(rootId: number, ancestors = false): Promise<GraphOut> {
    const { data } = await coreApi.get<GraphOut>('/graph', {
      params: { root_id: rootId, ancestors },
    })
    return data
  },
  /** Every live tree built from one template. */
  async byTemplate(templateId: number): Promise<GraphOut> {
    const { data } = await coreApi.get<GraphOut>('/graph', { params: { template_id: templateId } })
    return data
  },
  /** The hierarchy as the templates define it. */
  async templates(rootTemplateId?: number | null): Promise<GraphOut> {
    const { data } = await coreApi.get<GraphOut>('/graph/templates', {
      params: rootTemplateId ? { root_template_id: rootTemplateId } : {},
    })
    return data
  },
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------
export const auditApi = {
  async list(params: AuditQuery = {}): Promise<AuditOut[]> {
    const { data } = await coreApi.get<AuditOut[]>('/audit', { params })
    return data
  },
  async myItems(period: AuditPeriod): Promise<AuditOut[]> {
    const { data } = await coreApi.get<AuditOut[]>('/audit/my-items', { params: { period } })
    return data
  },
  /** The same filters as `list`, as an Excel workbook. */
  async export(params: AuditQuery = {}): Promise<Blob> {
    const { data } = await coreApi.get('/audit/export', { params, responseType: 'blob' })
    return data as Blob
  },
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------
export const usersApi = {
  async list(): Promise<User[]> {
    const { data } = await coreApi.get<User[]>('/users')
    return data
  },
  async managers(): Promise<UserBrief[]> {
    const { data } = await coreApi.get<UserBrief[]>('/users/managers')
    return data
  },
  async create(body: {
    email: string
    full_name: string
    password: string
    role: UserRole
  }): Promise<User> {
    const { data } = await coreApi.post<User>('/users', body)
    return data
  },
  async update(
    id: number,
    body: {
      full_name?: string
      role?: UserRole
      is_active?: boolean
      password?: string
      login_hint_visible?: boolean
      /** `''` withdraws a published password, leaving the email-only shortcut. */
      login_hint_password?: string
    },
  ): Promise<User> {
    const { data } = await coreApi.patch<User>(`/users/${id}`, body)
    return data
  },
  async remove(id: number): Promise<void> {
    await coreApi.delete(`/users/${id}`)
  },
}

// ---------------------------------------------------------------------------
// Import / Export
// ---------------------------------------------------------------------------
export const dataApi = {
  /** Import workbook: one sheet per template, headers = its creation fields. */
  async template(params: { template_id?: number; type?: ItemType } = {}): Promise<Blob> {
    const { data } = await coreApi.get('/data/template', { params, responseType: 'blob' })
    return data as Blob
  },
  async export(params: { template_id?: number; type?: ItemType } = {}): Promise<Blob> {
    const { data } = await coreApi.get('/data/export', { params, responseType: 'blob' })
    return data as Blob
  },
  /** All-or-nothing; a 400 carries `errors` (sheet + cell + reason). */
  async import(file: File): Promise<ImportResult> {
    const form = new FormData()
    form.append('file', file)
    // No explicit Content-Type: the browser must add the multipart boundary.
    const { data } = await coreApi.post<ImportResult>('/data/import', form)
    return data
  },
}

// ---------------------------------------------------------------------------
// Notifications (notification-service)
// ---------------------------------------------------------------------------
export const notificationsApi = {
  async list(
    params: { status?: NotificationStatus; limit?: number; offset?: number } = {},
  ): Promise<NotificationItem[]> {
    const { data } = await notificationApi.get<NotificationItem[]>('/notifications', { params })
    return data
  },
  async unreadCount(): Promise<number> {
    const { data } = await notificationApi.get<{ count: number }>('/notifications/unread-count')
    return data.count
  },
  async counts(): Promise<NotificationCounts> {
    const { data } = await notificationApi.get<NotificationCounts>('/notifications/count')
    return data
  },
  async markRead(id: number): Promise<void> {
    await notificationApi.post(`/notifications/${id}/read`)
  },
  async markAllRead(): Promise<void> {
    await notificationApi.post('/notifications/read-all')
  },
}
