<script setup>
// 执行日志面板：messages（✓）/ errors（⚠）
// 后端在 SSE 流式过程中只推 plan chunk，日志随 done 事件一次性返回，
// 因此流式期间显示脉冲占位。
defineProps({
  messages: { type: Array, default: () => [] },
  errors: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
})
</script>

<template>
  <aside class="log-panel card">
    <h2>执行日志</h2>
    <div class="log-body">
      <div v-if="running" class="log-running">
        <span class="pulse" />
        正在执行工作流…
      </div>
      <template v-else>
        <ul v-if="messages.length" class="log-list">
          <li v-for="(m, i) in messages" :key="i" class="log-ok">✓ {{ m }}</li>
        </ul>
        <ul v-if="errors.length" class="log-list">
          <li v-for="(e, i) in errors" :key="i" class="log-warn">⚠ {{ e }}</li>
        </ul>
        <p v-if="!messages.length && !errors.length" class="log-empty">暂无日志</p>
      </template>
    </div>
  </aside>
</template>
