import { describe, expect, test } from 'vitest'

import { getViewportMenuPosition, getViewportSidePanelPosition } from './floatingPanelPosition'

describe('getViewportMenuPosition', () => {
  test('moves the menu upward when it would overflow the viewport bottom', () => {
    expect(
      getViewportMenuPosition({
        anchorX: 400,
        anchorY: 760,
        panelWidth: 200,
        panelHeight: 280,
        viewportWidth: 1280,
        viewportHeight: 800,
      }),
    ).toEqual({
      left: 400,
      top: 508,
    })
  })

  test('keeps the menu position when it already fits', () => {
    expect(
      getViewportMenuPosition({
        anchorX: 200,
        anchorY: 180,
        panelWidth: 220,
        panelHeight: 240,
        viewportWidth: 1280,
        viewportHeight: 800,
      }),
    ).toEqual({
      left: 200,
      top: 180,
    })
  })
})

describe('getViewportSidePanelPosition', () => {
  test('flips the panel to the left when there is not enough room on the right', () => {
    expect(
      getViewportSidePanelPosition({
        anchorLeft: 980,
        anchorTop: 120,
        anchorWidth: 260,
        panelWidth: 300,
        panelHeight: 500,
        viewportWidth: 1280,
        viewportHeight: 900,
      }),
    ).toEqual({
      left: 660,
      top: 120,
      side: 'left',
    })
  })

  test('moves the panel upward when it would overflow the viewport bottom', () => {
    expect(
      getViewportSidePanelPosition({
        anchorLeft: 280,
        anchorTop: 540,
        anchorWidth: 260,
        panelWidth: 300,
        panelHeight: 500,
        viewportWidth: 1280,
        viewportHeight: 900,
      }),
    ).toEqual({
      left: 560,
      top: 384,
      side: 'right',
    })
  })
})
