// 健康状态：启动拉一次 + 定时轮询 + 手动刷新
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { getHealth } from '../api/health'
import { HEALTH_POLL_MS } from '../constants'

export function useHealth() {
  const status = ref('checking') // checking / ok / degraded / offline
  const health = ref(null)
  let timer = null

  async function refresh() {
    try {
      const data = await getHealth()
      health.value = data
      status.value = data?.status === 'ok' ? 'ok' : 'degraded'
    } catch {
      status.value = 'offline'
    }
  }

  onMounted(() => {
    refresh()
    timer = setInterval(refresh, HEALTH_POLL_MS)
  })

  onBeforeUnmount(() => clearInterval(timer))

  return { status, health, refresh }
}
