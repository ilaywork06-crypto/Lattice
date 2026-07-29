import { coreApi, notificationApi } from './client'
import type {
  AuditOut,
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
  LocationOut,
  LoginResponse,
  MapBuilding,
  MapBuildingCreate,
  MapBuildingUpdate,
  NotificationItem,
  SearchResults,
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
  async unlink(id: number): Promise<ItemOut> {
    const { data } = await coreApi.post<ItemOut>(`/items/${id}/unlink`, {})
    return data
  },
  async changeState(id: number, state: ItemState, note?: string): Promise<ItemOut> {
    const { data } = await coreApi.post<ItemOut>(`/items/${id}/state`, { state, note })
    return data
  },
  async addDocument(
    id: number,
    body: { name: string; url?: string; doc_type?: string },
  ): Promise<DocumentOut> {
    const { data } = await coreApi.post<DocumentOut>(`/items/${id}/documents`, body)
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
  async create(body: Partial<LocationOut>): Promise<LocationOut> {
    const { data } = await coreApi.post<LocationOut>('/locations', body)
    return data
  },
  async update(id: number, body: Partial<LocationOut>): Promise<LocationOut> {
    const { data } = await coreApi.patch<LocationOut>(`/locations/${id}`, body)
    return data
  },
  async remove(id: number): Promise<void> {
    await coreApi.delete(`/locations/${id}`)
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
  async get(rootId?: number): Promise<GraphOut> {
    const { data } = await coreApi.get<GraphOut>('/graph', {
      params: rootId ? { root_id: rootId } : {},
    })
    return data
  },
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------
export const auditApi = {
  async list(params: { item_id?: number; limit?: number } = {}): Promise<AuditOut[]> {
    const { data } = await coreApi.get<AuditOut[]>('/audit', { params })
    return data
  },
  async myItems(period: 'day' | 'week' | 'month'): Promise<AuditOut[]> {
    const { data } = await coreApi.get<AuditOut[]>('/audit/my-items', { params: { period } })
    return data
  },
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------
export const usersApi = {
  async list(): Promise<UserBrief[]> {
    const { data } = await coreApi.get<UserBrief[]>('/users')
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
    body: { full_name?: string; role?: UserRole; is_active?: boolean; password?: string },
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
  async template(type?: ItemType): Promise<Blob> {
    const { data } = await coreApi.get('/data/template', {
      params: type ? { type } : {},
      responseType: 'blob',
    })
    return data as Blob
  },
  async export(type?: ItemType): Promise<Blob> {
    const { data } = await coreApi.get('/data/export', {
      params: type ? { type } : {},
      responseType: 'blob',
    })
    return data as Blob
  },
  async import(file: File): Promise<ImportResult> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await coreApi.post<ImportResult>('/data/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
}

// ---------------------------------------------------------------------------
// Notifications (notification-service)
// ---------------------------------------------------------------------------
export const notificationsApi = {
  async list(params: { unread_only?: boolean; limit?: number } = {}): Promise<NotificationItem[]> {
    const { data } = await notificationApi.get<NotificationItem[]>('/notifications', { params })
    return data
  },
  async unreadCount(): Promise<number> {
    const { data } = await notificationApi.get<{ count: number }>('/notifications/unread-count')
    return data.count
  },
  async markRead(id: number): Promise<void> {
    await notificationApi.post(`/notifications/${id}/read`)
  },
  async markAllRead(): Promise<void> {
    await notificationApi.post('/notifications/read-all')
  },
}
