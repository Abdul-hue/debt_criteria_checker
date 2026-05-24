import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock window.scrollTo
window.scrollTo = vi.fn()

// Mock localStorage
const localStorageMock = (() => {
  let store = {}
  return {
    getItem: vi.fn((key) => store[key] || null),
    setItem: vi.fn((key, value) => {
      store[key] = value.toString()
    }),
    removeItem: vi.fn((key) => {
      delete store[key]
    }),
    clear: vi.fn(() => {
      store = {}
    }),
  }
})()
Object.defineProperty(window, 'localStorage', { value: localStorageMock })

// Mock jwt-decode
vi.mock('jwt-decode', () => ({
  jwtDecode: vi.fn(() => ({
    user_id: 1,
    email: 'test@test.com',
    is_admin: true,
    exp: 9999999999,
  })),
}))

// Global mock for ResizeObserver (needed for some Radix components)
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))
