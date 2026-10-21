import { API_BASE_URL } from '../config'
import type { Place, PlanRequest, PlanResponse } from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Flattens DRF error bodies ({detail} or {field: [msgs]}) into one readable line. */
function errorMessage(body: unknown, status: number): string {
  if (status === 429) return 'Too many requests. Please wait a minute and try again.'
  if (body && typeof body === 'object') {
    if ('detail' in body && typeof body.detail === 'string') return body.detail
    const parts = Object.entries(body).map(([field, value]) => {
      const text = Array.isArray(value) ? value.join(' ') : JSON.stringify(value)
      return field === 'non_field_errors' ? text : `${field}: ${text}`
    })
    if (parts.length) return parts.join(' · ')
  }
  return `Request failed (${status}).`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body: unknown = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(errorMessage(body, res.status), res.status)
  return body as T
}

export async function geocode(query: string, signal?: AbortSignal): Promise<Place[]> {
  const data = await request<{ results: Place[] }>(
    `/api/geocode?q=${encodeURIComponent(query)}`,
    { signal },
  )
  return data.results
}

export function planTrip(body: PlanRequest): Promise<PlanResponse> {
  return request<PlanResponse>('/api/plan', { method: 'POST', body: JSON.stringify(body) })
}
