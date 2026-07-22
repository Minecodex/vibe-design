import { afterEach, describe, it, expect } from 'vitest'
import { getImageUrl } from '@/utils/imageUrl'

afterEach(() => {
    delete window.__APP_CONFIG__
})

describe('imageUrl', () => {
    it('should return undefined if url is empty', () => {
        expect(getImageUrl()).toBeUndefined()
        expect(getImageUrl('')).toBeUndefined()
        expect(getImageUrl(null)).toBeUndefined()
    })

    it('should return the url unchanged if it starts with http', () => {
        const url = 'https://example.com/image.png'
        expect(getImageUrl(url)).toBe(url)
    })

    it('should prefix relative urls with base url domain', () => {
        const url = '/uploads/avatars/test.png'
        expect(getImageUrl(url)).toBe('http://localhost:8000/uploads/avatars/test.png')

        const url2 = 'uploads/avatars/test.png'
        expect(getImageUrl(url2)).toBe('http://localhost:8000/uploads/avatars/test.png')
    })

    it('should use runtime config api base url for relative urls', () => {
        window.__APP_CONFIG__ = {
            APP_API_BASE_URL: 'https://api.example.com/api/v1',
        }

        expect(getImageUrl('/uploads/avatars/test.png')).toBe('https://api.example.com/uploads/avatars/test.png')
    })
})
