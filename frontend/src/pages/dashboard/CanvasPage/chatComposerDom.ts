const BLOCK_CONTAINER_TAGS = new Set([
  'BLOCKQUOTE',
  'DIV',
  'LI',
  'OL',
  'P',
  'UL',
])

function isElementNode(node: Node | null): node is HTMLElement {
  return !!node && node.nodeType === Node.ELEMENT_NODE
}

function locateTrailingInsertionPoint(container: Node): { parent: Node, beforeNode: Node | null } {
  let current = container.lastChild

  while (current) {
    if (current.nodeType === Node.TEXT_NODE) {
      return { parent: container, beforeNode: current.nextSibling }
    }

    if (isElementNode(current)) {
      const element = current

      if (element.tagName === 'BR') {
        return { parent: container, beforeNode: element }
      }

      if (BLOCK_CONTAINER_TAGS.has(element.tagName)) {
        return locateTrailingInsertionPoint(element)
      }

      return { parent: container, beforeNode: element.nextSibling }
    }

    current = current.previousSibling
  }

  return { parent: container, beforeNode: null }
}

export function getAppendMentionInsertionPoint(root: HTMLElement): { parent: Node, beforeNode: Node | null } {
  return locateTrailingInsertionPoint(root)
}

export function getManualMentionInsertionPoint(root: HTMLElement, anchorNode: Node): { parent: Node, beforeNode: Node | null } {
  const parent = anchorNode.parentNode
  if (!parent) return { parent: root, beforeNode: null }
  if (parent !== root) return { parent, beforeNode: anchorNode.nextSibling }

  let previousSibling = anchorNode.previousSibling
  while (previousSibling) {
    if (isElementNode(previousSibling) && BLOCK_CONTAINER_TAGS.has(previousSibling.tagName)) {
      return locateTrailingInsertionPoint(previousSibling)
    }
    previousSibling = previousSibling.previousSibling
  }

  return { parent: root, beforeNode: anchorNode.nextSibling }
}

export function moveCursorAfterNode(node: Node) {
  const selection = window.getSelection()
  if (!selection) return

  const range = document.createRange()
  if (node.nodeType === Node.TEXT_NODE) {
    range.setStart(node, node.textContent?.length ?? 0)
  } else {
    range.setStartAfter(node)
  }
  range.collapse(true)
  selection.removeAllRanges()
  selection.addRange(range)
}

function isAtomicChipNode(node: Node | null): node is HTMLElement {
  return !!node
    && node.nodeType === Node.ELEMENT_NODE
    && (((node as HTMLElement).hasAttribute('data-mark-id')) || ((node as HTMLElement).hasAttribute('data-mention-id')))
}

function isCaretWhitespace(text: string) {
  return /^[\s\u00A0\u200B]*$/.test(text)
}

export function removeAtomicChipBeforeCaret(root: HTMLElement): { markId: string | null, mentionId: string | null } | null {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return null

  const range = selection.getRangeAt(0)
  if (!range.collapsed || !root.contains(range.startContainer)) return null

  const startContainer = range.startContainer
  const startOffset = range.startOffset

  let chip: HTMLElement | null = null
  let caretContainer: Node = root
  let caretOffset = 0

  if (startContainer.nodeType === Node.TEXT_NODE) {
    const textNode = startContainer as Text
    const text = textNode.textContent || ''
    const beforeCaret = text.slice(0, startOffset)
    const afterCaret = text.slice(startOffset)

    if (!isCaretWhitespace(beforeCaret)) {
      return null
    }

    const previousSibling = textNode.previousSibling
    if (!isAtomicChipNode(previousSibling)) {
      return null
    }

    chip = previousSibling
    const parent = chip.parentNode
    if (!parent) return null

    const chipIndex = Array.from(parent.childNodes).indexOf(chip)
    chip.remove()

    if (afterCaret.length > 0) {
      textNode.textContent = afterCaret
      caretContainer = textNode
      caretOffset = 0
    } else if (textNode.parentNode) {
      textNode.remove()
      caretContainer = parent
      caretOffset = Math.min(chipIndex, parent.childNodes.length)
    } else {
      caretContainer = parent
      caretOffset = Math.min(chipIndex, parent.childNodes.length)
    }
  } else if (startContainer.nodeType === Node.ELEMENT_NODE) {
    const element = startContainer as HTMLElement
    const previousNode = element.childNodes[startOffset - 1] ?? null

    if (isAtomicChipNode(previousNode)) {
      chip = previousNode
    } else if (previousNode?.nodeType === Node.TEXT_NODE && isCaretWhitespace(previousNode.textContent || '')) {
      const textNode = previousNode as Text
      const candidateChip = textNode.previousSibling
      if (!isAtomicChipNode(candidateChip)) {
        return null
      }

      chip = candidateChip
      textNode.remove()
    } else {
      return null
    }

    const parent = chip.parentNode
    if (!parent) return null

    const chipIndex = Array.from(parent.childNodes).indexOf(chip)
    chip.remove()
    caretContainer = parent
    caretOffset = Math.min(chipIndex, parent.childNodes.length)
  } else {
    return null
  }

  const nextRange = document.createRange()
  nextRange.setStart(caretContainer, caretOffset)
  nextRange.collapse(true)
  selection.removeAllRanges()
  selection.addRange(nextRange)

  return {
    markId: chip.getAttribute('data-mark-id'),
    mentionId: chip.getAttribute('data-mention-id'),
  }
}
