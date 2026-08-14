// 全局 toast 管理（轻量，无外部依赖）
import { ref } from 'vue'

let seq = 0

export function useToast() {
  const toasts = ref([])

  function toast(type = 'info', message) {
    const id = ++seq
    toasts.value.push({ id, type, message })
    setTimeout(() => dismiss(id), 3500)
  }

  function dismiss(id) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  return { toasts, toast, dismiss }
}
