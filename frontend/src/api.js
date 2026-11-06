// Talks to the Flask API. Every change-making request carries the X-SpendU
// header — the server rejects requests without it (CSRF protection).

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

export async function api(path, { method = 'GET', body, form } = {}) {
  const options = { method, headers: { 'X-SpendU': '1' }, credentials: 'same-origin' }
  if (form) {
    options.body = form
  } else if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch('/api' + path, options)
  } catch {
    throw new ApiError("Can't reach the server. Check your connection.", 0)
  }
  if (res.status === 401 && !path.startsWith('/auth/login')) {
    window.dispatchEvent(new Event('spendu:signed-out'))
  }
  const isJson = (res.headers.get('content-type') || '').includes('json')
  const data = isJson ? await res.json() : await res.text()
  if (!res.ok) throw new ApiError((data && data.error) || 'Something went wrong.', res.status)
  return data
}

export const get = (path) => api(path)
export const post = (path, body = {}) => api(path, { method: 'POST', body })
export const patch = (path, body = {}) => api(path, { method: 'PATCH', body })
export const del = (path) => api(path, { method: 'DELETE' })

export function query(params) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, v)
  })
  const s = q.toString()
  return s ? '?' + s : ''
}
