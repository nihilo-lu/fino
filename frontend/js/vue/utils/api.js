/**
 * 带认证的 API 请求封装
 * 使用 Session Cookie；API 脚本可用 Bearer Token
 */
const API_BASE = '/api'

export async function apiFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) }
  const response = await fetch(url, { ...options, headers, credentials: 'include' })
  if (response.status === 401) {
    return { ok: false, unauthorized: true }
  }
  return response
}

export async function apiGet(path, params = {}) {
  const query = new URLSearchParams(params).toString()
  const url = query ? `${API_BASE}${path}?${query}` : `${API_BASE}${path}`
  return apiFetch(url)
}

export async function apiPost(path, body) {
  return apiFetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
}

export async function apiPut(path, body) {
  return apiFetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
}

export async function apiDelete(path) {
  return apiFetch(`${API_BASE}${path}`, { method: 'DELETE' })
}

export { API_BASE }
