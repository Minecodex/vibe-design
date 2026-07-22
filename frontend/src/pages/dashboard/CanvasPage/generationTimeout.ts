export const IMAGE_GENERATION_POLL_TIMEOUT_MS = 30 * 60 * 1000
export const VIDEO_GENERATION_POLL_TIMEOUT_MS = 5 * 60 * 60 * 1000

export function getGenerationPollTimeoutMs(mediaType: 'image' | 'video'): number {
    return mediaType === 'image'
        ? IMAGE_GENERATION_POLL_TIMEOUT_MS
        : VIDEO_GENERATION_POLL_TIMEOUT_MS
}
