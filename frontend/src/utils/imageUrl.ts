import { getApiOrigin } from '@/config/runtimeConfig'

export const getImageUrl = (url?: string | null): string | undefined => {
    if (!url) return undefined
    if (url.startsWith('http')) return url

    const prefix = getApiOrigin()

    // Ensure we don't duplicate slashes
    return `${prefix}${url.startsWith('/') ? '' : '/'}${url}`
}
