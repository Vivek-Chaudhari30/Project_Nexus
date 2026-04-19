import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setToken, getToken, clearToken } from '../lib/api'

// localStorage stub
const store: Record<string, string> = {}
vi.stubGlobal('localStorage', {
  getItem: (k: string) => store[k] ?? null,
  setItem: (k: string, v: string) => { store[k] = v },
  removeItem: (k: string) => { delete store[k] },
})

beforeEach(() => {
  for (const k of Object.keys(store)) delete store[k]
})

describe('token helpers', () => {
  it('setToken stores token', () => {
    setToken('abc123')
    expect(getToken()).toBe('abc123')
  })

  it('clearToken removes token', () => {
    setToken('abc123')
    clearToken()
    expect(getToken()).toBeNull()
  })

  it('getToken returns null when no token set', () => {
    expect(getToken()).toBeNull()
  })
})
