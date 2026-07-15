// Shared low-level HTTP helpers for the Mission Control API client (#19 split).
export type ApiErrorCode = 'http_error' | 'backend_mismatch' | 'invalid_response'

export class ApiError extends Error {
  status: number
  code: ApiErrorCode
  path: string
  detail?: unknown

  constructor(message: string, status: number, code: ApiErrorCode, path: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.path = path
    this.detail = detail
  }
}

async function responsePayload(res: Response, path: string): Promise<any> {
  if (res.status === 204) return null
  const text = await res.text()
  if (!text.trim()) return null
  try {
    return JSON.parse(text)
  } catch {
    const contentType = (res.headers.get('content-type') || '').toLowerCase()
    const html = contentType.includes('text/html') || text.trimStart().startsWith('<')
    if (html) {
      throw new ApiError(
        'Mission Control UI and backend are out of sync. Restart the current MC backend, then reload this page.',
        res.ok ? 502 : res.status,
        'backend_mismatch',
        path,
      )
    }
    throw new ApiError('Mission Control returned an unreadable API response.', res.ok ? 502 : res.status, 'invalid_response', path)
  }
}

function throwHttpError(res: Response, path: string, payload: any): never {
  const detail = payload?.detail
  throw new ApiError(typeof detail === 'string' ? detail : `HTTP ${res.status}`, res.status, 'http_error', path, detail)
}

export async function get(path: string) {
  const res = await fetch(path, { cache: 'no-cache' })
  const payload = await responsePayload(res, path)
  if (!res.ok) throwHttpError(res, path, payload)
  return payload
}

export async function request(path: string, init: RequestInit) {
  const isFormData = init.body instanceof FormData
  const res = await fetch(path, {
    cache: 'no-cache',
    ...init,
    // headers must come AFTER ...init so a caller's headers merge *into* the
    // defaults instead of replacing them (otherwise Content-Type is lost → 422).
    // For FormData bodies we must NOT set Content-Type — the browser needs to
    // set multipart/form-data with its own boundary or FastAPI rejects the upload.
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init.headers || {}),
    },
  })
  const payload = await responsePayload(res, path)
  if (!res.ok) throwHttpError(res, path, payload)
  return payload
}
