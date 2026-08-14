<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'checking' }, // checking / ok / degraded / offline
  health: { type: Object, default: null },
})
const emit = defineEmits(['refresh'])

const STATUS_TEXT = {
  checking: '检测中',
  ok: '服务正常',
  degraded: '服务降级',
  offline: '后端不可达',
}

const statusText = computed(() => STATUS_TEXT[props.status] || props.status)

const tooltipLines = computed(() => {
  const h = props.health
  if (!h) return []
  const lines = [`API Key：${h.api_key_set ? '已配置' : '未配置'}`]
  if (h.models) lines.push(`模型：${h.models.planner}`)
  if (h.tools) {
    lines.push(
      `工具：高德${h.tools.amap ? '✓' : '✗'} · 百度${h.tools.baidu ? '✓' : '✗'} · 博查${h.tools.bocha ? '✓' : '✗'}`
    )
  }
  if (h.infra) {
    lines.push(
      `基础设施：Redis${h.infra.redis_enabled ? '✓' : '✗'} · MySQL${h.infra.db_enabled ? '✓' : '✗'} · RAG${h.infra.rag_enabled ? '✓' : '✗'}`
    )
  }
  return lines
})
</script>

<template>
  <button
    class="health-badge"
    :class="status"
    :title="tooltipLines.join('\n')"
    @click="emit('refresh')"
  >
    <span class="health-dot" />
    {{ statusText }}
  </button>
</template>
