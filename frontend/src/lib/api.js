// Thin fetch wrapper around the FastAPI backend.
// In dev, Vite proxies /api and /media to http://localhost:8000 (see vite.config.js).
// Set VITE_API_URL (e.g. http://localhost:8000) to call the backend directly instead.
const BASE = import.meta.env.VITE_API_URL || '/api'
const MEDIA_BASE = import.meta.env.VITE_API_URL || ''

export const apiUrl = (path) => `${BASE}${path}`
export const media = (u) => (!u ? null : u.startsWith('http') ? u : `${MEDIA_BASE}${u}`)

async function request(path, opts = {}) {
  let res
  try {
    res = await fetch(apiUrl(path), opts)
  } catch {
    throw new Error(`Cannot reach the RoadPulse backend at ${BASE}. Is the API server running?`)
  }
  // A non-JSON 404 means the request hit a static host (e.g. Vercel) instead of the FastAPI backend
  if (res.status === 404 && !(res.headers.get('content-type') || '').includes('json')) {
    throw new Error(
      `Backend not found at ${BASE}. This site is only the dashboard: deploy the backend (Hugging Face Space / Docker) ` +
      'and set VITE_API_URL to its address, then redeploy.',
    )
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      msg = body.detail || msg
    } catch { /* not JSON */ }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json()
}

const qs = (params = {}) => {
  const p = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length))
  return p.length ? '?' + new URLSearchParams(p.map(([k, v]) => [k, Array.isArray(v) ? v.join(',') : v])).toString() : ''
}

export const api = {
  config: () => request('/config'),
  stats: () => request('/stats'),
  reports: (params) => request('/reports' + qs(params)),
  sites: (params) => request('/sites' + qs(params)),
  site: (id) => request(`/sites/${id}`),
  ranking: (params) => request('/ranking' + qs(params)),
  rankingCsvUrl: (params) => apiUrl('/ranking.csv' + qs(params)),
  uploads: () => request('/uploads'),
  upload: (formData) => request('/upload', { method: 'POST', body: formData }),
  setUploadLocation: (id, lat, lon) =>
    request(`/uploads/${id}/location`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lat, lon }) }),
  review: (reportId, body) =>
    request(`/review/${reportId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  reviewSite: (siteId, body) =>
    request(`/sites/${siteId}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  evaluate: (refresh = false) => request('/evaluate' + qs({ refresh: refresh || undefined })),
}
