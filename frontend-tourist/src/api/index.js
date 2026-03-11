import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 60000, // 增加超时时间，适应 RAG 查询可能较长的情况
  headers: {
    'Content-Type': 'application/json'
  }
})

// 可复用的“按 key 取消在途请求”工具：用于 TTS/轮询/搜索等，避免慢网堆积拖慢 UI
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
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

api.interceptors.response.use(
  response => {
    return response
  },
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default api

