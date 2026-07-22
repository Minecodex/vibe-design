import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CanvasLeftToolbar } from './CanvasLeftToolbar'

const baseProps = {
  isGuest: false,
  isDark: false,
  tools: [
    { key: 'select', label: 'Select', svgPath: <span>Select</span> },
    { key: 'image_gen', label: 'Image Generator', svgPath: <span>Image</span> },
    { key: 'video_gen', label: 'Video Generator', svgPath: <span>Video</span> },
  ],
  selectTools: [{ key: 'select', label: 'Select', svgPath: <span>Select</span>, shortcut: 'V' }],
  addTools: [],
  activeTool: 'hand',
  setActiveTool: vi.fn(),
  isSelectMenuOpen: false,
  setIsSelectMenuOpen: vi.fn(),
  hoveredSelectTool: null,
  setHoveredSelectTool: vi.fn(),
  isAddMenuOpen: false,
  setIsAddMenuOpen: vi.fn(),
  hoveredAddTool: null,
  setHoveredAddTool: vi.fn(),
  addNewGenerator: vi.fn(),
  imageInputRef: { current: null },
  videoInputRef: { current: null },
  setIsAssetLibraryOpen: vi.fn(),
}

describe('CanvasLeftToolbar', () => {
  it('switches to select after adding an image generator', () => {
    const setActiveTool = vi.fn()
    const addNewGenerator = vi.fn()

    render(
      <CanvasLeftToolbar
        {...baseProps}
        setActiveTool={setActiveTool}
        addNewGenerator={addNewGenerator}
      />,
    )

    fireEvent.click(screen.getByTitle('Image Generator'))

    expect(setActiveTool).toHaveBeenCalledWith('select')
    expect(addNewGenerator).toHaveBeenCalledWith('image_generator')
  })

  it('switches to select after adding a video generator', () => {
    const setActiveTool = vi.fn()
    const addNewGenerator = vi.fn()

    render(
      <CanvasLeftToolbar
        {...baseProps}
        setActiveTool={setActiveTool}
        addNewGenerator={addNewGenerator}
      />,
    )

    fireEvent.click(screen.getByTitle('Video Generator'))

    expect(setActiveTool).toHaveBeenCalledWith('select')
    expect(addNewGenerator).toHaveBeenCalledWith('video_generator')
  })
})
