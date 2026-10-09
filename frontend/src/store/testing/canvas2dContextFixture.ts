// jsdom has no native 2D renderer. These tests observe a small drawing surface;
// GPU context requests must remain unsupported rather than pretending to be 2D.
export function installCanvas2dContextFixture(context: object) {
  const original = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, 'getContext')!
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true, writable: true,
    value: (kind: string) => kind === '2d' ? context : null,
  })
  return { mockRestore: () => Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', original) }
}
