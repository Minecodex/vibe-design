export const GENERATION_ARTIFACT_REFERENCE_SCHEME = 'generation-artifact-reference:'

const ARTIFACT_REF_PATTERN = /\bartifact_ref:[A-Za-z0-9_-]+/g

export function encodeGenerationArtifactReferenceHref(artifactRef: string): string {
  return `${GENERATION_ARTIFACT_REFERENCE_SCHEME}${encodeURIComponent(normalizeGenerationArtifactRef(artifactRef) || artifactRef)}`
}

export function decodeGenerationArtifactReferenceHref(href: string | null | undefined): string | null {
  const value = String(href || '').trim()
  if (value.startsWith(GENERATION_ARTIFACT_REFERENCE_SCHEME)) {
    try {
      return normalizeGenerationArtifactRef(decodeURIComponent(value.slice(GENERATION_ARTIFACT_REFERENCE_SCHEME.length)))
    } catch {
      return normalizeGenerationArtifactRef(value.slice(GENERATION_ARTIFACT_REFERENCE_SCHEME.length))
    }
  }
  return normalizeGenerationArtifactRef(value)
}

export function normalizeGenerationArtifactRef(value: string | null | undefined): string | null {
  const trimmed = String(value || '').trim().replace(/[，。！？、；：,.!?;:]+$/u, '')
  const match = trimmed.match(/^artifact_ref:[A-Za-z0-9_-]+$/)
  return match ? match[0] : null
}

export function createGenerationArtifactReferenceRemarkPlugin() {
  return () => (tree: Record<string, any>) => {
    visitMarkdownTextNodes(tree, splitTextWithGenerationArtifactReferenceLinks)
  }
}

function splitTextWithGenerationArtifactReferenceLinks(text: string): Array<Record<string, any>> {
  const nodes: Array<Record<string, any>> = []
  let cursor = 0

  ARTIFACT_REF_PATTERN.lastIndex = 0
  for (const match of text.matchAll(ARTIFACT_REF_PATTERN)) {
    const token = normalizeGenerationArtifactRef(match[0])
    const index = match.index ?? 0
    if (!token) {
      continue
    }

    if (index > cursor) {
      nodes.push({ type: 'text', value: text.slice(cursor, index) })
    }
    nodes.push({
      type: 'link',
      url: encodeGenerationArtifactReferenceHref(token),
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
