export interface ModifierState {
  altKey: boolean
  metaKey: boolean
  ctrlKey: boolean
}

export function isMarkModifierPressed(modifierState: ModifierState): boolean {
  return modifierState.altKey || modifierState.metaKey
}

export function isTransientMarkModeActive({
  activeTool,
  isHoveringMarkableImage,
  modifierState,
}: {
  activeTool: string
  isHoveringMarkableImage: boolean
  modifierState: ModifierState
}): boolean {
  return activeTool === 'select' && isHoveringMarkableImage && isMarkModifierPressed(modifierState)
}
