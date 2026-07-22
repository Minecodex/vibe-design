export const CANVAS_WORKSPACE_FILE_REFERENCE_SCHEME = 'canvas-workspace-file-reference:'

const MEDIA_EXTENSIONS = [
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'bmp',
  'svg',
  'avif',
  'mp4',
  'webm',
  'mov',
  'm4v',
  'avi',
  'mkv',
] as const

const MEDIA_EXTENSION_PATTERN = [...MEDIA_EXTENSIONS].sort((a, b) => b.length - a.length).join('|')
const WORKSPACE_MEDIA_TOKEN_PATTERN = new RegExp(
  String.raw`(?:sandbox:\/+)?(?:(?:code\/files|files|references\/(?:inputs|sources|generated)|file_versions|project|published|skill|code)\/)?[^\s"'<>()[\]{}]+?\.(${MEDIA_EXTENSION_PATTERN})`,
  'gi',
)

export function createCanvasWorkspaceFileReferenceRemarkPlugin() {
  return () => (tree: Record<string, any>) => {
    visitMarkdownTextNodes(tree, splitTextWithWorkspaceFileReferenceLinks)
  }
}

export function encodeCanvasWorkspaceFileReferenceHref(filePath: string): string {
  return `${CANVAS_WORKSPACE_FILE_REFERENCE_SCHEME}${encodeURIComponent(trimWorkspaceMediaReference(filePath))}`
}

export function decodeCanvasWorkspaceFileReferenceHref(href: string | null | undefined): string | null {
  const raw = String(href || '').trim()
  if (raw.startsWith(CANVAS_WORKSPACE_FILE_REFERENCE_SCHEME)) {
    try {
      return normalizeWorkspaceMediaReference(decodeURIComponent(raw.slice(CANVAS_WORKSPACE_FILE_REFERENCE_SCHEME.length)))
    } catch {
      return normalizeWorkspaceMediaReference(raw.slice(CANVAS_WORKSPACE_FILE_REFERENCE_SCHEME.length))
    }
  }
  return normalizeWorkspaceMediaReference(raw)
}

export function normalizeWorkspaceMediaReference(value: string | null | undefined): string | null {
  const trimmed = trimWorkspaceMediaReference(value)
  if (!trimmed || isExternalReference(trimmed)) {
    return null
  }
  const extension = getExtension(trimmed)
  if (!MEDIA_EXTENSIONS.includes(extension as typeof MEDIA_EXTENSIONS[number])) {
    return null
  }
  return trimmed.replace(/^sandbox:\/+/i, '').replace(/^\/+/, '').replace(/\\/g, '/')
}

export function inferCanvasWorkspaceMediaKind(filePath: string): 'image' | 'video' {
  const extension = getExtension(filePath)
  return ['mp4', 'webm', 'mov', 'm4v', 'avi', 'mkv'].includes(extension) ? 'video' : 'image'
}

function splitTextWithWorkspaceFileReferenceLinks(text: string): Array<Record<string, any>> {
  const nodes: Array<Record<string, any>> = []
  let cursor = 0

  WORKSPACE_MEDIA_TOKEN_PATTERN.lastIndex = 0
  for (const match of text.matchAll(WORKSPACE_MEDIA_TOKEN_PATTERN)) {
    const token = normalizeWorkspaceMediaReference(match[0])
    const index = match.index ?? 0
    if (!token) {
      continue
    }
    if (index > cursor) {
      nodes.push({ type: 'text', value: text.slice(cursor, index) })
    }
    nodes.push({
      type: 'link',
      url: encodeCanvasWorkspaceFileReferenceHref(token),
      title: null,
      children: [{ type: 'text', value: token }],
    })
    cursor = index + match[0].length
  }

  if (nodes.length === 0) {
    return [{ type: 'text', value: text }]
  }
  if (cursor < text.length) {
    nodes.push({ type: 'text', value: text.slice(cursor) })
  }
  return nodes
}

function visitMarkdownTextNodes(
  node: Record<string, any>,
  transformText: (text: string) => Array<Record<string, any>>,
) {
  if (!node || typeof node !== 'object' || !Array.isArray(node.children)) {
    return
  }
  if (['link', 'image', 'code', 'inlineCode'].includes(String(node.type || ''))) {
    return
  }

  const nextChildren: Array<Record<string, any>> = []
  for (const child of node.children) {
    if (child?.type === 'text' && typeof child.value === 'string') {
      nextChildren.push(...transformText(child.value))
      continue
    }
    visitMarkdownTextNodes(child, transformText)
    nextChildren.push(child)
  }
  node.children = nextChildren
}

function trimWorkspaceMediaReference(value: string | null | undefined): string {
  return String(value || '').trim().replace(/[，。！？、；：,.!?;:]+$/u, '')
}

function isExternalReference(value: string): boolean {
  return /^(https?:|data:|blob:)/i.test(value)
}

function getExtension(filePath: string): string {
  return String(filePath || '').split(/[?#]/)[0]?.split('.').pop()?.toLowerCase() || ''
}
