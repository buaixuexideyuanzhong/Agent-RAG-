// 通用 fetch 封装：统一 base URL + 非 2xx 错误归一化（读 FastAPI 的 detail）
export const BASE_URL = import.meta.env.VITE_API_BASE || '/api/v1'

export async function httpGet(path) {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw await toHttpError(res)
  return res.json()
}

export async function httpPost(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await toHttpError(res)
  return res.json()
}

async function toHttpError(res) {
  let detail = ''
  try {
    const data = await res.json()
    detail = data?.detail || ''
  } catch {
    // 响应体不是 JSON，忽略
  }
  const msg = detail
    ? (typeof detail === 'string' ? detail : JSON.stringify(detail))
    : `HTTP ${res.status} ${res.statusText}`
  return new Error(msg)
}
