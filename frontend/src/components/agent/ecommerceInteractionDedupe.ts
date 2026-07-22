import type { MessageBlock as CanvasMessageBlock } from '@/store/canvasAgentStore'
import type { MessageBlock as HomeMessageBlock } from '@/store/homeHarnessStore'

type EcommerceMessageBlock = CanvasMessageBlock | HomeMessageBlock
type EcommerceChatMessage<TBlock extends EcommerceMessageBlock> = {
  blocks?: TBlock[] | null
}

export function dedupeEcommerceInteractionBlocks<T extends EcommerceMessageBlock>(blocks: T[]): T[] {
  return blocks
}

export function dedupeEcommerceInteractionMessages<
  TBlock extends EcommerceMessageBlock,
  TMessage extends EcommerceChatMessage<TBlock>,
>(messages: TMessage[]): TMessage[] {
  return messages
}
