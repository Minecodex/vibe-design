import type { ComponentProps } from 'react'
import type { TFunction } from 'i18next'
import type { CanvasItem } from '@/api/endpoints/projects'
import { CanvasBrushToolPanel } from './CanvasBrushToolPanel'
import { CanvasBrushToolbar } from './CanvasBrushToolbar'
import { CanvasLeftToolbar } from './CanvasLeftToolbar'
import { CanvasTextToolbar } from './CanvasTextToolbar'
import { CanvasWorkspaceBottomBar } from './CanvasWorkspaceBottomBar'
import { CanvasWorkspaceCanvasArea } from './CanvasWorkspaceCanvasArea'

type TextToolbarProps = ComponentProps<typeof CanvasTextToolbar>
type BrushToolbarProps = ComponentProps<typeof CanvasBrushToolbar>
type BrushPanelProps = ComponentProps<typeof CanvasBrushToolPanel>
type CanvasWorkspaceProps = ComponentProps<typeof CanvasLeftToolbar>
  & ComponentProps<typeof CanvasWorkspaceBottomBar>
  & Record<string, unknown>
  & {
    t: TFunction
    selectedSingleItem: CanvasItem | null
    selectedSingleItemRect: TextToolbarProps['rect'] | null
    textToolbarState: TextToolbarProps['state']
    setTextToolbarState: TextToolbarProps['setState']
    updateTextStyle: TextToolbarProps['updateTextStyle']
    brushToolState: BrushPanelProps['state']
    setBrushToolState: BrushPanelProps['setState']
    brushToolbarState: BrushToolbarProps['state']
    setBrushToolbarState: BrushToolbarProps['setState']
    updateBrushItem: BrushToolbarProps['updateBrushItem']
  }

export function CanvasWorkspace(props: CanvasWorkspaceProps) {
  const { isGuest, isDark, tools, selectTools, addTools, activeTool, setActiveTool, isSelectMenuOpen, setIsSelectMenuOpen, hoveredSelectTool, setHoveredSelectTool, isAddMenuOpen, setIsAddMenuOpen, hoveredAddTool, setHoveredAddTool, addNewGenerator, imageInputRef, videoInputRef, setIsAssetLibraryOpen, zoom, zoomIn, zoomOut, t, isLayerPanelOpen, setIsLayerPanelOpen, selectedSingleItem, selectedSingleItemRect, textToolbarState, setTextToolbarState, brushToolState, setBrushToolState, brushToolbarState, setBrushToolbarState, updateTextStyle, updateBrushItem } = props

  const textToolbarLabels = {
    fill: t('canvas.text_toolbar.fill', '濉厖'),
    stroke: t('canvas.text_toolbar.stroke', '鎻忚竟'),
    font: t('canvas.text_toolbar.font', '瀛椾綋'),
    variant: t('canvas.text_toolbar.variant', '瀛楅噸'),
    size: t('canvas.text_toolbar.size', '瀛楀彿'),
    align: t('canvas.text_toolbar.align', '瀵归綈'),
    more: t('canvas.text_toolbar.more', '鏇村'),
    vertical: t('canvas.text_toolbar.vertical', '绔栨帓'),
  }

  const brushToolbarLabels = {
    color: t('canvas.brush_toolbar.color', 'Color'),
    size: t('canvas.brush_toolbar.size', 'Size'),
    width: t('canvas.brush_toolbar.width', 'W'),
    height: t('canvas.brush_toolbar.height', 'H'),
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}>
      <div style={{ flex: 1, display: 'flex', position: 'relative', overflow: 'hidden' }}>
        <CanvasLeftToolbar
          isGuest={isGuest}
          isDark={isDark}
          tools={tools}
          selectTools={selectTools}
          addTools={addTools}
          activeTool={activeTool}
          setActiveTool={setActiveTool}
          isSelectMenuOpen={isSelectMenuOpen}
          setIsSelectMenuOpen={setIsSelectMenuOpen}
          hoveredSelectTool={hoveredSelectTool}
          setHoveredSelectTool={setHoveredSelectTool}
          isAddMenuOpen={isAddMenuOpen}
          setIsAddMenuOpen={setIsAddMenuOpen}
          hoveredAddTool={hoveredAddTool}
          setHoveredAddTool={setHoveredAddTool}
          addNewGenerator={addNewGenerator}
          imageInputRef={imageInputRef}
          videoInputRef={videoInputRef}
          setIsAssetLibraryOpen={setIsAssetLibraryOpen}
        />
        <CanvasBrushToolPanel
          isDark={isDark}
          activeTool={activeTool}
          state={brushToolState}
          setState={setBrushToolState}
          brushToolIndex={tools.findIndex((tool) => tool.key === 'brush')}
          totalTools={tools.length}
        />

        <CanvasWorkspaceCanvasArea {...props} />
      </div>

      {selectedSingleItem?.type === 'text' && selectedSingleItemRect && (
        <CanvasTextToolbar
          item={selectedSingleItem}
          rect={selectedSingleItemRect}
          isDark={isDark}
          labels={textToolbarLabels}
          state={textToolbarState}
          setState={setTextToolbarState}
          updateTextStyle={updateTextStyle}
        />
      )}

      {selectedSingleItem?.type === 'brush_path' && selectedSingleItemRect && (
        <CanvasBrushToolbar
          item={selectedSingleItem}
          rect={selectedSingleItemRect}
          isDark={isDark}
          colorLabel={brushToolbarLabels.color}
          sizeLabel={brushToolbarLabels.size}
          widthLabel={brushToolbarLabels.width}
          heightLabel={brushToolbarLabels.height}
          state={brushToolbarState}
          setState={setBrushToolbarState}
          updateBrushItem={updateBrushItem}
        />
      )}

      <CanvasWorkspaceBottomBar
        isDark={isDark}
        isLayerPanelOpen={isLayerPanelOpen}
        setIsLayerPanelOpen={setIsLayerPanelOpen}
        zoomOut={zoomOut}
        zoom={zoom}
        zoomIn={zoomIn}
        t={t}
      />
    </div>
  )
}
