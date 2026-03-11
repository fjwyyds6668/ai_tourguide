import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 可复用的“按 key 取消在途请求”工具：用于轮询/搜索联想等，避免慢网堆积拖慢 UI
const _inflight = new Map()
export function cancelInflight(key) {
  const ctrl = _inflight.get(key)
  if (ctrl) {
    try { ctrl.abort() } catch (_) {}
    _inflight.delete(key)
  }
}
export function withAbort(key, config = {}) {
  if (typeof AbortController === 'undefined') return config
  cancelInflight(key)
  const ctrl = new AbortController()
  _inflight.set(key, ctrl)
  return { ...config, signal: ctrl.signal }
}

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error)
    if (error.response?.status === 401 && !error.config?.url?.includes('/auth/login')) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
