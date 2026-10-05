import axios, { type AxiosInstance, type AxiosError } from 'axios'

// ---------------------------------------------------------------------------
// Central axios configuration. Two backends: the core API and the
// notification service. Both validate the same Bearer JWT.
// ---------------------------------------------------------------------------

const CORE_API_URL = import.meta.env.VITE_CORE_API_URL || 'http://localhost:8000'
const NOTIFICATION_API_URL =
  import.meta.env.VITE_NOTIFICATION_API_URL || 'http://localhost:8001'

const TOKEN_KEY = 'lattice.access_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/**
 * Called by the response interceptor on a 401. Wired up by the auth store so we
 * avoid a circular import (client ↔ store).
 */
let onUnauthorized: (() => void) | null = null
export function registerUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn
}

function attachInterceptors(instance: AxiosInstance): AxiosInstance {
  instance.interceptors.request.use((config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  instance.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      if (error.response?.status === 401 && onUnauthorized) {
        onUnauthorized()
      }
      return Promise.reject(error)
    },
  )

  return instance
}

export const coreApi = attachInterceptors(
  axios.create({ baseURL: CORE_API_URL }),
)

export const notificationApi = attachInterceptors(
  axios.create({ baseURL: NOTIFICATION_API_URL }),
)

/**
 * Extract a human-readable message from an axios error, preferring the
 * backend's `detail` field (FastAPI convention).
 */
export function extractError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      // FastAPI validation error array
      return detail
        .map((d: { msg?: string; loc?: unknown[] }) => {
          const loc = Array.isArray(d.loc) ? d.loc.slice(1).join('.') : ''
          return loc ? `${loc}: ${d.msg}` : d.msg
        })
        .filter(Boolean)
        .join('; ')
    }
    if (error.message) return error.message
  }
  if (error instanceof Error) return error.message
  return 'An unexpected error occurred'
}

/** Structured problems a 400 may carry next to `detail` (per form field, or
 *  per spreadsheet cell on an import). */
export interface ApiErrorEntry {
  field?: string
  label?: string
  sheet?: string
  cell?: string | null
  row?: number | null
  column?: string | null
  error: string
}

export function extractErrorList(error: unknown): ApiErrorEntry[] {
  if (axios.isAxiosError(error)) {
    const errors = (error.response?.data as { errors?: unknown } | undefined)?.errors
    if (Array.isArray(errors)) return errors as ApiErrorEntry[]
  }
  return []
}

export { CORE_API_URL, NOTIFICATION_API_URL }
