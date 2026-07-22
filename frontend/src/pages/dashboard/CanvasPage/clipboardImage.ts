export function getClipboardImageFile(clipboardData?: DataTransfer | null) {
  if (!clipboardData) return null

  const files = Array.from(clipboardData.files || [])
  const fileMatch = files.find((file) => file.type.startsWith('image/'))
  if (fileMatch) return fileMatch

  const items = Array.from(clipboardData.items || [])
  const itemMatch = items.find((item) => item.kind === 'file' && item.type.startsWith('image/'))
  return itemMatch?.getAsFile() || null
}

export function canReadSystemClipboardImages() {
  return typeof navigator !== 'undefined' && typeof navigator.clipboard?.read === 'function'
}

export async function readClipboardImageFileFromNavigator() {
  if (!canReadSystemClipboardImages()) {
    console.info('[canvas paste] navigator.clipboard.read not available')
    return null
  }

  const clipboardItems = await navigator.clipboard.read()
  console.info('[canvas paste] clipboard items:', clipboardItems.map((item) => item.types))
  for (const clipboardItem of clipboardItems) {
    const imageType = clipboardItem.types.find((type) => type.startsWith('image/'))
    if (!imageType) continue
    const blob = await clipboardItem.getType(imageType)
    return new File([blob], `clipboard-image.${imageType.split('/')[1] || 'png'}`, { type: imageType })
  }

  return null
}

export async function hasClipboardImageInNavigator() {
  if (!canReadSystemClipboardImages()) return false

  const clipboardItems = await navigator.clipboard.read()
  return clipboardItems.some((clipboardItem) => clipboardItem.types.some((type) => type.startsWith('image/')))
}
