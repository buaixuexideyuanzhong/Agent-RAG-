// 策划流程状态机：idle / streaming / done / error
// 串起 SSE 流式调用、中止取消、done 结果对齐
import { ref, computed } from 'vue'
import { planStream } from '../api/plan'

export function usePlanner() {
  const status = ref('idle')
  const planText = ref('') // 流式增量拼接的文本
  const result = ref(null) // done 事件的完整 PlanResponse
  const errorMsg = ref('') // error 文案

  let activeCancel = null

  const isStreaming = computed(() => status.value === 'streaming')

  async function start(request) {
    cancel() // 防重入
    status.value = 'streaming'
    planText.value = ''
    result.value = null
    errorMsg.value = ''

    // 注意：解构出的 cancel 是 planStream 返回的 abort 函数，必须改名，
    // 否则会遮蔽外层 function cancel()，导致下方 start() 开头调用 cancel() 时命中 TDZ
    const { promise, cancel: abortStream } = planStream(request, {
      onChunk: (delta) => {
        planText.value += delta
      },
    })
    activeCancel = abortStream

    try {
      const res = await promise
      result.value = res
      // 用 done 事件返回的完整 plan 作为对齐基准，避免分块拼接边界问题
      planText.value = res?.plan ?? planText.value
      if (res?.success) {
        status.value = 'done'
      } else {
        status.value = 'error'
        errorMsg.value = res?.error || '策划未成功'
      }
    } catch (e) {
      if (e?.message === '已取消') {
        // 用户主动中止：静默复位，不弹错误
        status.value = 'idle'
      } else {
        status.value = 'error'
        errorMsg.value = e?.message || String(e)
      }
    } finally {
      activeCancel = null
    }
  }

  function cancel() {
    if (activeCancel) {
      const c = activeCancel
      activeCancel = null
      c()
    }
  }

  function reset() {
    cancel()
    status.value = 'idle'
    planText.value = ''
    result.value = null
    errorMsg.value = ''
  }

  return { status, isStreaming, planText, result, errorMsg, start, cancel, reset }
}
