// Shared low-level HTTP helpers for the Mission Control API client (#19 split).
export async function get(path: string) {
  const res = await fetch(path, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
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
  if (!res.ok) {
    const maybeJson = await res.json().catch(() => null)
    const detail = maybeJson?.detail
    const err: any = new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`)
    err.status = res.status
    err.detail = detail
    throw err
  }
  if (res.status === 204) return null
  return res.json()
}
