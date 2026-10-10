export function canvasViewportFixture(width = 1200, height = 800) {
  const element = document.createElement('div')
  Object.defineProperties(element, {
    clientWidth: { value: width },
    clientHeight: { value: height },
  })
  element.getBoundingClientRect = () => new DOMRect(0, 0, width, height)
  return { current: element }
}
