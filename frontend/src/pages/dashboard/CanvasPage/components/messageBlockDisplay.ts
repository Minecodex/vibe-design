import type { MessageBlock } from '@/store/canvasAgentTypes'
import { dedupeEcommerceInteractionBlocks } from '@/components/agent/ecommerceInteractionDedupe'

export function extractAnalyzeImageText(source: unknown): string {
    if (typeof source === 'string') {
        const text = source.trim()
        if (!text) {
            return ''
        }
        if (!text.startsWith('{')) {
            return text
        }
        try {
            const parsed = JSON.parse(text)
            if (parsed && typeof parsed.analysis === 'string' && parsed.analysis.trim().length > 0) {
                return parsed.analysis
            }
            if (parsed && typeof parsed.description === 'string' && parsed.description.trim().length > 0) {
                return parsed.description
            }
            if (parsed && typeof parsed.message === 'string' && parsed.message.trim().length > 0) {
                return parsed.message
            }
        } catch {
            return text
        }
        return text
    }

    if (!source || typeof source !== 'object') {
        return ''
    }

    const record = source as Record<string, unknown>
    const text = record.analysis || record.description || record.message || record.content
    if (typeof text === 'string' && text.trim().length > 0) {
        return text
    }

    try {
        return JSON.stringify(source)
    } catch {
        return ''
    }
}

function normalizeCanvasToolName(name: unknown): string {
    return String(name || '').replace(/^lc_/, '')
}

function extractCanvasAnalyzeImageCallId(block: MessageBlock): string | null {
    const payloadCallId = String(block.payload.call_id || '').trim()
    if (payloadCallId) {
        return payloadCallId
    }

    if (typeof block.id === 'string' && block.id.startsWith('tool-')) {
        return block.id.slice('tool-'.length)
    }
    if (typeof block.id === 'string' && block.id.startsWith('media-')) {
        return block.id.slice('media-'.length)
    }
    if (typeof block.id === 'string' && block.id.startsWith('analyze-image-text-')) {
        return block.id.slice('analyze-image-text-'.length)
    }

    return null
}

function isCanvasAnalyzeImageTextBlock(block: MessageBlock): boolean {
    const toolName = normalizeCanvasToolName(block.payload.tool_name)
    return toolName === 'analyze_image' && (block.kind === 'text' || block.uiKind === 'text' || block.uiKind === 'assistant_text')
}

function isCanvasAnalyzeImageStreamPanel(block: MessageBlock): boolean {
    return block.uiKind === 'stream_panel' && normalizeCanvasToolName(block.payload.tool_name) === 'analyze_image'
}

function isCanvasImageAnalysisMediaCard(block: MessageBlock): boolean {
    return block.uiKind === 'media_card' && String(block.payload.media_type || '') === 'image_analysis'
}

function blocksShareCanvasAnalyzeImageIdentity(left: MessageBlock, right: MessageBlock): boolean {
    const leftCallId = extractCanvasAnalyzeImageCallId(left)
    const rightCallId = extractCanvasAnalyzeImageCallId(right)
    return !!leftCallId && leftCallId === rightCallId
}

function extractCanvasAnalyzeImageBlockText(block: MessageBlock | undefined): string {
    if (!block) {
        return ''
    }

    if (isCanvasAnalyzeImageTextBlock(block)) {
        return extractAnalyzeImageText(String(block.payload.text || ''))
    }

    if (isCanvasAnalyzeImageStreamPanel(block)) {
        return extractAnalyzeImageText(
            block.payload.stream_text
            || block.payload.text
            || block.payload.result
            || '',
        )
    }

    if (isCanvasImageAnalysisMediaCard(block)) {
        return extractAnalyzeImageText(
            block.payload.text
            || block.payload.analysis
            || block.payload.result
            || '',
        )
    }

    return ''
}

function mergeCanvasAnalyzeImageBlocks(blocks: MessageBlock[]): MessageBlock[] {
    const mediaCards = blocks.filter(isCanvasImageAnalysisMediaCard)
    if (mediaCards.length === 0) {
        return blocks
    }

    return blocks.flatMap((block) => {
        if (isCanvasImageAnalysisMediaCard(block)) {
            const childCompanions = (block.children || [])
                .filter((candidate) => blocksShareCanvasAnalyzeImageIdentity(block, candidate))
            const siblingCompanions = blocks
                .filter((candidate) => candidate !== block && blocksShareCanvasAnalyzeImageIdentity(block, candidate))
            const companions = [...childCompanions, ...siblingCompanions]
            const companionText = companions.find(isCanvasAnalyzeImageTextBlock)
            const companionPanel = companions.find(isCanvasAnalyzeImageStreamPanel)
            const mergedText = (
                extractCanvasAnalyzeImageBlockText(companionPanel)
                || extractCanvasAnalyzeImageBlockText(companionText)
                || extractCanvasAnalyzeImageBlockText(block)
            )
            const elapsedMs = Number(
                companionPanel?.payload.elapsed_ms
                ?? companionPanel?.payload.result?.elapsed_ms
                ?? block.payload.elapsed_ms
                ?? block.payload.result?.elapsed_ms
                ?? 0,
            )

            return [{
                ...block,
                payload: {
                    ...block.payload,
                    text: mergedText,
                    analysis: mergedText || block.payload.analysis,
                    elapsed_ms: Number.isFinite(elapsedMs) && elapsedMs > 0 ? elapsedMs : block.payload.elapsed_ms,
                },
            }]
        }

        if ((isCanvasAnalyzeImageTextBlock(block) || isCanvasAnalyzeImageStreamPanel(block))
            && mediaCards.some((mediaCard) => blocksShareCanvasAnalyzeImageIdentity(mediaCard, block))) {
            return []
        }

        return [block]
    })
}

export function buildRenderableBlocks(blocks: MessageBlock[]): {
    blocks: MessageBlock[]
    mirroredChildBlockIds: Set<string>
} {
    const nextBlocks: MessageBlock[] = []
    const mirroredChildBlockIds = new Set<string>()
    const sortedBlocks = dedupeEcommerceInteractionBlocks(mergeCanvasAnalyzeImageBlocks(
        [...blocks].sort((a, b) => a.order - b.order),
    ))

    sortedBlocks.forEach((block) => {
        nextBlocks.push(block)

        if (block.uiKind !== 'subagent_card') {
            return
        }

        const childBlocks = [...(block.children || [])]
            .filter((child) => child.visible !== false && child.uiKind === 'generation_task')
            .sort((a, b) => a.order - b.order)

        if (childBlocks.length === 0) {
            return
        }

        childBlocks.forEach((childBlock) => {
            mirroredChildBlockIds.add(childBlock.id)
            nextBlocks.push({
                ...childBlock,
                id: `mirror-${block.id}-${childBlock.id}`,
            })
        })
    })

    return {
        blocks: nextBlocks.map((block, index) => ({ ...block, order: index })),
        mirroredChildBlockIds,
    }
}

export function formatReplyTimestamp(value: string | null | undefined) {
    if (!value) return ''
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    const now = new Date()
    const timeSegment = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
    const isSameDay = date.getFullYear() === now.getFullYear()
        && date.getMonth() === now.getMonth()
        && date.getDate() === now.getDate()

    if (isSameDay) {
        return timeSegment
    }

    return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${timeSegment}`
}

