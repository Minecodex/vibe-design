import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

const BASE_URL = 'http://localhost:8000/api/v1'

export const handlers = [
  http.post(`${BASE_URL}/auth/login`, () => {
    return HttpResponse.json({
      access_token: 'mock-access-token',
      refresh_token: 'mock-refresh-token',
      token_type: 'bearer',
      user: {
        id: 1,
        email: 'test@example.com',
        username: 'testuser',
        role: 'user',
        is_active: true,
      },
    })
  }),

  http.post(`${BASE_URL}/auth/register`, () => {
    return HttpResponse.json(
      {
        success: true,
        message: 'register success',
        data: {
          id: 2,
          email: 'new@example.com',
          username: 'newuser',
          role: 'user',
          is_active: true,
        },
      },
      { status: 201 }
    )
  }),

  http.get(`${BASE_URL}/auth/me`, () => {
    return HttpResponse.json({
      success: true,
      message: 'ok',
      data: {
        id: 1,
        email: 'test@example.com',
        username: 'testuser',
        role: 'user',
        is_active: true,
      },
    })
  }),

  http.post(`${BASE_URL}/auth/logout`, () => {
    return HttpResponse.json({ success: true, message: 'logout success', data: null })
  }),

  http.get(`${BASE_URL}/health`, () => {
    return HttpResponse.json({
      status: 'healthy',
      env: 'development',
      app: '像素重组',
      deploy_type: 'private',
      license_expired: false,
      license_expires_at: '2099-12-31T23:59:59+08:00',
    })
  }),

  http.get(`${BASE_URL}/public-config`, () => {
    return HttpResponse.json({
      app_name: '像素重组',
      app_name_en: 'Pixel Reorganization',
      upload_limits: {
        avatar_max_bytes: 5 * 1024 * 1024,
        canvas_image_max_bytes: 20 * 1024 * 1024,
        canvas_video_max_bytes: 500 * 1024 * 1024,
        harness_attachment_max_bytes: 50 * 1024 * 1024,
      },
    })
  }),

  http.post(`${BASE_URL}/license/activate`, () => {
    return HttpResponse.json({
      expires_at: '2099-12-31T23:59:59+08:00',
      expired: false,
    })
  }),
]

export const server = setupServer(...handlers)
