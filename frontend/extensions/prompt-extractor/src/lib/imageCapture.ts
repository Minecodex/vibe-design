function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = ''
  const bytes = new Uint8Array(buffer)
  for (let index = 0; index < bytes.byteLength; index += 1) {
    binary += String.fromCharCode(bytes[index])
  }
  return btoa(binary)
}

export async function fetchImageAsDataUrl(imageUrl: string): Promise<string> {
  const response = await fetch(imageUrl)
  if (!response.ok) {
    throw new Error('无法读取图片')
  }

  const blob = await response.blob()
  const buffer = await blob.arrayBuffer()
  return `data:${blob.type || 'image/png'};base64,${arrayBufferToBase64(buffer)}`
}
