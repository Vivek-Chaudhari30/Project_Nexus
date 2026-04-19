// REST client — all calls go through apiFetch which injects the Bearer token.
// Token is stored in localStorage under the key 'nexus_token'.

import type {
  CreateSessionResponse,
  LoginResponse,
  RegisterResponse,
  SessionDetail,
  SessionList,
  UserProfile,
} from './types'

const BASE = '/api/v1'
const TOKEN_KEY = 'nexus_token'

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body?.detail ?? `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as unknown as T
  return res.json() as Promise<T>
}

// ── Auth ──────────────────────────────────────────────────────────────────

export async function register(email: string, password: string): Promise<RegisterResponse> {
  return apiFetch('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  return apiFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export async function me(): Promise<UserProfile> {
  return apiFetch('/auth/me')
}

// ── Sessions ──────────────────────────────────────────────────────────────

export async function createSession(goal: string): Promise<CreateSessionResponse> {
  return apiFetch('/sessions', {
    method: 'POST',
    body: JSON.stringify({ goal }),
  })
}

export async function listSessions(limit = 20, offset = 0): Promise<SessionList> {
  return apiFetch(`/sessions?limit=${limit}&offset=${offset}`)
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  return apiFetch(`/sessions/${sessionId}`)
}

export async function deleteSession(sessionId: string): Promise<void> {
  return apiFetch(`/sessions/${sessionId}`, { method: 'DELETE' })
}

export async function abortSession(sessionId: string): Promise<void> {
  return apiFetch(`/sessions/${sessionId}/abort`, { method: 'POST' })
}
