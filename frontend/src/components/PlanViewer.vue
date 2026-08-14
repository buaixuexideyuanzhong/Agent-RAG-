<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { renderPlan } from '../utils/markdown'
import { formatBudget } from '../utils/format'

const props = defineProps({
  status: { type: String, default: 'idle' }, // idle / streaming / done / error
  plan: { type: String, default: '' },
  result: { type: Object, default: null },
  error: { type: String, default: '' },
  saving: { type: Boolean, default: false },
})
const emit = defineEmits(['save', 'notify'])

const viewport = ref(null)
const html = ref('') // 完整行渲染后的 HTML
const tail = ref('') // 未完成行（纯文本打字尾巴）
const stickyBottom = ref(true)
let rafId = null

const hasPlan = computed(() => !!props.plan)
const canSave = computed(
  () => props.status === 'done' && props.result?.success && !!props.plan && !props.saving
)

// 需求摘要 chips
const chips = computed(() => {
  const r = props.result?.requirements
  if (!r) return []
  const list = []
  if (r.activity_type) list.push(r.activity_type)
  if (r.theme) list.push(r.theme)
  if (r.attendee_count != null) list.push(`${r.attendee_count}人`)
  if (r.budget != null) list.push(formatBudget(r.budget))
  if (r.city) list.push(r.city)
  if (r.preferred_area) list.push(r.preferred_area)
  if (r.time) list.push(r.time)
  if (r.duration) list.push(r.duration)
  return list
})

// 只渲染"完整行"，最后一行留作纯文本尾巴，避免半行表格/半个加粗闪烁
function renderNow() {
  const p = props.plan || ''
  const nl = p.lastIndexOf('\n')
  const complete = nl >= 0 ? p.slice(0, nl + 1) : ''
  tail.value = nl >= 0 ? p.slice(nl + 1) : p
  html.value = renderPlan(complete)
  if (stickyBottom.value) {
    nextTick(() => {
      const el = viewport.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }
}

// rAF 节流：合并同帧增量，一帧最多渲染一次
watch(
  () => props.plan,
  () => {
    cancelAnimationFrame(rafId)
    rafId = requestAnimationFrame(renderNow)
  },
  { immediate: true }
)

function onScroll() {
  const el = viewport.value
  if (!el) return
  stickyBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 60
}

async function copy() {
  const text = props.result?.plan || props.plan
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    emit('notify', { type: 'success', message: '已复制到剪贴板' })
  } catch {
    emit('notify', { type: 'error', message: '复制失败，请手动选择复制' })
  }
}

onBeforeUnmount(() => cancelAnimationFrame(rafId))
</script>

<template>
  <section class="plan-viewer card">
    <div class="viewer-header">
      <h2>策划方案</h2>
      <div class="viewer-actions">
        <span v-if="status === 'streaming'" class="streaming-indicator">生成中…</span>
        <button class="btn" :disabled="!hasPlan" @click="copy">复制</button>
        <button class="btn btn-primary" :disabled="!canSave" @click="emit('save')">
          {{ saving ? '保存中…' : '保存到案例库' }}
        </button>
      </div>
    </div>

    <div v-if="chips.length" class="req-chips">
      <span v-for="(c, i) in chips" :key="i" class="chip">{{ c }}</span>
    </div>

    <div ref="viewport" class="viewer-body" @scroll="onScroll">
      <div v-if="!plan && status === 'idle'" class="placeholder">
        填写需求后点击「开始策划」，方案将在此处实时生成
      </div>
      <div v-else-if="status === 'error'" class="error-box">❌ {{ error || '策划失败' }}</div>
      <template v-else-if="plan || status === 'streaming' || status === 'done'">
        <div class="md" v-html="html" />
        <span v-if="tail" class="md-tail">{{ tail }}</span>
        <span v-if="status === 'streaming'" class="caret" />
      </template>
    </div>

    <div class="details">
      <details v-if="result?.venue_info" class="detail-panel">
        <summary>🏢 场地信息</summary>
        <div class="detail-body" v-html="renderPlan(result.venue_info)" />
      </details>
      <details v-if="result?.supplier_info" class="detail-panel">
        <summary>🤝 商家资源</summary>
        <div class="detail-body" v-html="renderPlan(result.supplier_info)" />
      </details>
      <details v-if="result?.process_info" class="detail-panel">
        <summary>📋 流程参考</summary>
        <div class="detail-body" v-html="renderPlan(result.process_info)" />
      </details>
    </div>
  </section>
</template>
