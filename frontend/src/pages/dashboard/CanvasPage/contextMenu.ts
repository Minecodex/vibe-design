export interface CanvasContextMenuItem {
  key?: string
  label?: string
  shortcut?: string
  type?: 'divider'
}

interface CanvasSelectionMenuLabels {
  copy: string
  paste: string
  restore: string
  bringForward: string
  sendBackward: string
  bringFront: string
  sendBack: string
  createGroup: string
  mergeLayers: string
  ungroup: string
  toggleVisible: string
  lock: string
  export: string
  delete: string
  photoshopEdit: string
}

interface BuildCanvasSelectionMenuItemsOptions {
  firstSelectedItemType?: string | null
  selectedItemIds: string[]
  allSelectedItemsAreMediaWithUrl: boolean
  selectionCanMerge: boolean
  currentSelectionHasImage: boolean
  currentSelectionSupportsPhotoshopEdit?: boolean
  labels?: Partial<CanvasSelectionMenuLabels>
}

export function buildCanvasSelectionMenuItems({
  firstSelectedItemType,
  selectedItemIds,
  allSelectedItemsAreMediaWithUrl,
  selectionCanMerge,
  currentSelectionSupportsPhotoshopEdit = false,
  labels: customLabels,
}: BuildCanvasSelectionMenuItemsOptions): CanvasContextMenuItem[] {
  const labels: CanvasSelectionMenuLabels = {
    copy: '复制',
    paste: '粘贴',
    restore: '尺寸还原',
    bringForward: '上移一层',
    sendBackward: '下移一层',
    bringFront: '移动至顶层',
    sendBack: '移动至底层',
    createGroup: '创建编组',
    mergeLayers: '合并图层',
    ungroup: '解除编组',
    toggleVisible: '显示/隐藏',
    lock: '锁定/解锁',
    export: '导出',
    delete: '删除',
    photoshopEdit: 'PS 编辑',
    ...customLabels,
  }
  const isGroupSelected = firstSelectedItemType === 'group'
  const isMulti = selectedItemIds.length > 1

  const baseItems: CanvasContextMenuItem[] = [
    { key: 'copy', label: labels.copy, shortcut: 'Ctrl + C' },
    { key: 'paste', label: labels.paste, shortcut: 'Ctrl + V' },
  ]

  if (!isMulti && allSelectedItemsAreMediaWithUrl && (firstSelectedItemType === 'image' || firstSelectedItemType === 'video')) {
    baseItems.push({ key: 'restore', label: labels.restore })
  }

  if (currentSelectionSupportsPhotoshopEdit) {
    baseItems.push({ key: 'ps_edit', label: labels.photoshopEdit })
  }

  baseItems.push(
    { type: 'divider' },
    { key: 'bring_forward', label: labels.bringForward, shortcut: 'Ctrl + ]' },
    { key: 'send_backward', label: labels.sendBackward, shortcut: 'Ctrl + [' },
    { key: 'bring_front', label: labels.bringFront, shortcut: ']' },
    { key: 'send_back', label: labels.sendBack, shortcut: '[' },
  )

  if (isMulti) {
    baseItems.push({ type: 'divider' })
    baseItems.push({ key: 'create_group', label: labels.createGroup, shortcut: 'Ctrl + G' })
    if (selectionCanMerge) {
      baseItems.push({ key: 'merge_layers', label: labels.mergeLayers })
    }
  }

  if (isGroupSelected) {
    baseItems.push({ type: 'divider' })
    baseItems.push({ key: 'ungroup', label: labels.ungroup, shortcut: 'Shift + Ctrl + G' })
  }

  baseItems.push({ type: 'divider' })
  baseItems.push({ key: 'toggle_visible', label: labels.toggleVisible, shortcut: 'Shift + Ctrl + Y' })
  baseItems.push({ key: 'lock', label: labels.lock, shortcut: 'Shift + Ctrl + L' })
  baseItems.push({ type: 'divider' })
  baseItems.push({ key: 'export', label: labels.export })
  baseItems.push({ key: 'delete', label: labels.delete })

  return baseItems
}
