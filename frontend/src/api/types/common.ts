export interface ApiResponse<T = unknown> {
  success: boolean
  message: string
  data: T
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ApiError {
  detail: string | ValidationError[]
  status_code?: number
}

export interface ValidationError {
  loc: string[]
  msg: string
  type: string
}
