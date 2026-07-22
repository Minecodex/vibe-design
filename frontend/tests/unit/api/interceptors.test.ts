import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { setupInterceptors } from '@/api/interceptors'
import { storage } from '@/utils/storage'

vi.mock('@/utils/storage', () => ({
    storage: {
        getToken: vi.fn(),
        getRefreshToken: vi.fn(),
        setToken: vi.fn(),
        setRefreshToken: vi.fn(),
        clearTokens: vi.fn(),
    },
}))

vi.mock('@/i18n', () => ({
    default: {
        language: 'zh-CN',
    },
}))

describe('interceptors', () => {
    let client = axios.create({ baseURL: 'http://localhost:8000/api/v1' })

    beforeEach(() => {
        client = axios.create({ baseURL: 'http://localhost:8000/api/v1' })
        setupInterceptors(client)
        vi.clearAllMocks()

        // Mock adapter to prevent actual requests and "Invalid base URL" errors
        client.defaults.adapter = vi.fn().mockResolvedValue({
            data: {},
            status: 200,
            statusText: 'OK',
            headers: {},
            config: {} as any
        })

        // More stable window.location mock
        const location = new URL('http://localhost:3000')
        Object.defineProperty(window, 'location', {
            writable: true,
            value: {
                ...location,
                assign: vi.fn(),
                replace: vi.fn(),
                reload: vi.fn(),
            }
        })
    })


    it('should add Authorization header if token exists', async () => {
        vi.mocked(storage.getToken).mockReturnValue('mock-token')

        await client.get('/test')
        const adapter = client.defaults.adapter as any
        const config = adapter.mock.calls[0][0]

        expect(config.headers?.Authorization).toBe('Bearer mock-token')
        expect(config.headers?.['Accept-Language']).toBe('zh-CN')
    })


    it('should add Accept-Language header even if no token', async () => {
        vi.mocked(storage.getToken).mockReturnValue(null)

        await client.get('/test')
        const adapter = client.defaults.adapter as any
        const config = adapter.mock.calls[0][0]

        expect(config.headers?.Authorization).toBeUndefined()
        expect(config.headers?.['Accept-Language']).toBe('zh-CN')
    })


    it('should not retry if error is not 401', async () => {
        const error = new Error('Network Error') as AxiosError
        error.response = { status: 500, data: 'Error', statusText: 'Internal', headers: {}, config: {} as any }

        // Manually trigger the response error interceptor hook
        const responseInterceptor = (client.interceptors.response as any).handlers[0].rejected
        await expect(responseInterceptor(error)).rejects.toThrow('Network Error')
    })

    it('should redirect to activation page on license expiration without clearing tokens', async () => {
        const reqConfig = { url: '/projects', headers: {} } as InternalAxiosRequestConfig
        const error = new Error('Forbidden') as AxiosError
        error.response = {
            status: 403,
            data: { code: 'LICENSE_EXPIRED', detail: 'license expired' },
            statusText: 'Forbidden',
            headers: {},
            config: reqConfig,
        }
        error.config = reqConfig

        const responseInterceptor = (client.interceptors.response as any).handlers[0].rejected
        await expect(responseInterceptor(error)).rejects.toThrow('Forbidden')

        expect(storage.clearTokens).not.toHaveBeenCalled()
        expect(window.location.href).toBe('/activation')
    })

    it('should redirect to login if no refresh token on 401', async () => {
        vi.mocked(storage.getRefreshToken).mockReturnValue(null)

        const reqConfig = { url: '/test', headers: {} } as InternalAxiosRequestConfig
        const error = new Error('Unauthorized') as AxiosError
        error.response = { status: 401, data: '', statusText: 'Unauthorized', headers: {}, config: reqConfig }
        error.config = reqConfig

        const responseInterceptor = (client.interceptors.response as any).handlers[0].rejected
        await expect(responseInterceptor(error)).rejects.toThrow()
        expect(storage.clearTokens).toHaveBeenCalled()
        expect(window.location.href).toBe('/?login=true')
    })

    it('should refresh token and retry request on 401', async () => {
        vi.mocked(storage.getRefreshToken).mockReturnValue('valid-refresh-token')

        const reqConfig = { url: '/test', headers: {} } as InternalAxiosRequestConfig
        const error = new Error('Unauthorized') as AxiosError
        error.response = { status: 401, data: '', statusText: 'Unauthorized', headers: {}, config: reqConfig }
        error.config = reqConfig

        // Mock client.post for the refresh call
        const postSpy = vi.spyOn(client, 'post').mockResolvedValueOnce({
            data: { access_token: 'new-token', refresh_token: 'new-refresh-token' }
        } as any)

        const responseInterceptor = (client.interceptors.response as any).handlers[0].rejected
        await responseInterceptor(error)

        expect(postSpy).toHaveBeenCalledWith('/auth/refresh', { refresh_token: 'valid-refresh-token' })
        expect(storage.setToken).toHaveBeenCalledWith('new-token')
        expect(storage.setRefreshToken).toHaveBeenCalledWith('new-refresh-token')

        expect(reqConfig.headers.Authorization).toBe('Bearer new-token')

        const adapter = client.defaults.adapter as any
        // Filter calls to avoid counting the initial failure if it was somehow tracked
        // but here we only care about the retry. 
        // Actually, since we clear mocks or create new client, it should be clean.
        // client.post calls adapter too.
        expect(adapter).toHaveBeenCalled()
        const retryCall = adapter.mock.calls.find((call: any) => call[0].url === '/test')
        expect(retryCall).toBeDefined()
        expect(retryCall[0].headers.Authorization).toBe('Bearer new-token')
    })


    it('should redirect to login if refresh token fails', async () => {
        vi.mocked(storage.getRefreshToken).mockReturnValue('valid-refresh-token')

        const reqConfig = { url: '/test', headers: {} } as InternalAxiosRequestConfig
        const error = new Error('Unauthorized') as AxiosError
        error.response = { status: 401, data: '', statusText: 'Unauthorized', headers: {}, config: reqConfig }
        error.config = reqConfig

        // Mock client.post to fail
        vi.spyOn(client, 'post').mockRejectedValueOnce(new Error('Refresh failed'))

        const responseInterceptor = (client.interceptors.response as any).handlers[0].rejected
        await expect(responseInterceptor(error)).rejects.toThrow()

        expect(storage.clearTokens).toHaveBeenCalled()
        expect(window.location.href).toBe('/?login=true')
    })
})
