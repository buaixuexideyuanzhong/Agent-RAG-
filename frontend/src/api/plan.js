// SSE 流式策划：POST /api/v1/plan/stream
// 后端不发心跳，需求提取 + 并行搜索可能静默 30~60s 才吐第一个 chunk，
// 因此用"无数据超时"（每收到一帧重置），而非总时长超时。
//
// 返回 { promise, cancel }：
//   - promise 在 done 事件 resolve(result)，在 error 事件 / 超时 / 取消 / 网络错误时 reject(Error)
//   - cancel() 中止底层 fetch（用户中止按钮 / 组件卸载时调用）
import { SSE_TIMEOUT_MS } from '../constants'
import { parseSseFrame } from '../utils/sse'

export function planStream(request, { onChunk, timeoutMs = SSE_TIMEOUT_MS } = {}) {
  const controller = new AbortController()
  let timedOut = false
  let watchdog = null

  const armWatchdog = () => {
    clearTimeout(watchdog)
    watchdog = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, timeoutMs)
  }

  // 取消 / 超时 / 网络错误三分，全部归一为可读 Error
  const friendly = (e) => {
    if (controller.signal.aborted) {
      return timedOut ? new Error('流式响应超时，已中止') : new Error('已取消')
    }
    if (e?.message) return new Error(`网络错误：${e.message}`)
    return new Error('网络错误：连接中断')
  }

  const promise = (async () => {
    let res
    try {
      res = await fetch('/api/v1/plan/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request }),
        signal: controller.signal,
      })
    } catch (e) {
      throw friendly(e)
    }

    if (!res.ok || !res.body) {
      let detail = ''
      try {
        detail = (await res.json()).detail || ''
      } catch {
        // 响应体不是 JSON，忽略
      }
      throw new Error(`HTTP ${res.status} ${res.statusText}${detail ? `：${detail}` : ''}`)
    }

    armWatchdog()
    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8') // 流式增量解码，保证中文跨 chunk 不乱码
    let buffer = ''
    let gotDone = false

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let idx
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          const evt = parseSseFrame(frame)
          if (!evt) continue
          armWatchdog() // 收到任何数据帧即续命
          if (evt.type === 'chunk') {
            if (onChunk) onChunk(evt.delta || '')
          } else if (evt.type === 'done') {
            gotDone = true
            return evt.result
          } else if (evt.type === 'error') {
            throw new Error(evt.error || '后端返回错误')
          }
        }
        if (gotDone) break
      }
      if (!gotDone) throw new Error('连接提前结束，未收到完成事件')
    } catch (e) {
      throw friendly(e)
    } finally {
      try {
        reader.releaseLock()
      } catch {
        // reader 已释放
      }
      clearTimeout(watchdog)
    }
  })()

  return { promise, cancel: () => controller.abort() }
}
