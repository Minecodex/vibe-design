export const HOME_CHAT_PPT_REGENERATE_SLIDE_MESSAGE = 'home_harness_ppt_regenerate_slide'
export const HOME_CHAT_PPT_REGENERATE_STATE_MESSAGE = 'home_harness_ppt_regenerate_state'

export interface HomeChatPptRegenerateSlideMessage {
  type: typeof HOME_CHAT_PPT_REGENERATE_SLIDE_MESSAGE
  slideIndex: number
}

export interface HomeChatPptRegenerateStateMessage {
  type: typeof HOME_CHAT_PPT_REGENERATE_STATE_MESSAGE
  disabled: boolean
}

export function isHomeChatPptRegenerateSlideMessage(
  data: unknown,
): data is HomeChatPptRegenerateSlideMessage {
  return (
    !!data
    && typeof data === 'object'
    && (data as { type?: unknown }).type === HOME_CHAT_PPT_REGENERATE_SLIDE_MESSAGE
    && Number.isInteger((data as { slideIndex?: unknown }).slideIndex)
    && Number((data as { slideIndex?: unknown }).slideIndex) > 0
  )
}
