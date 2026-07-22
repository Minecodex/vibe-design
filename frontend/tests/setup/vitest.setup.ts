import '@testing-library/jest-dom'
import { beforeAll, afterAll, afterEach } from 'vitest'
import { server } from './msw-handlers'

// jsdom does not implement object URLs; stub them so components that preview
// local files (e.g. canvas chat attachments) work under test.
if (typeof URL.createObjectURL !== 'function') {
  let objectUrlSeq = 0
  URL.createObjectURL = () => `blob:vitest/${objectUrlSeq++}`
  URL.revokeObjectURL = () => {}
}

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
