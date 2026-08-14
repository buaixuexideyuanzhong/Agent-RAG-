<script setup>
import { ref, onBeforeUnmount } from 'vue'
import HealthBadge from './components/HealthBadge.vue'
import PlanningInput from './components/PlanningInput.vue'
import PlanViewer from './components/PlanViewer.vue'
import LogPanel from './components/LogPanel.vue'
import ToastHost from './components/ToastHost.vue'
import { usePlanner } from './composables/usePlanner'
import { useHealth } from './composables/useHealth'
import { useToast } from './composables/useToast'
import { saveCase } from './api/cases'
import { pickMeta, clipId } from './utils/format'
import { INPUT_MAX_LENGTH } from './constants'

const planner = usePlanner()
const { status: plannerStatus, isStreaming, planText, result, errorMsg } = planner
const { status: healthStatus, health: healthData, refresh: refreshHealth } = useHealth()
const { toasts, toast, dismiss } = useToast()

const requestText = ref('')
const saving = ref(false)

async function onSubmit(text) {
  await planner.start(text)
}

async function onSave() {
  const res = result.value
  if (!res?.success || !res?.plan) return
  saving.value = true
  try {
    const meta = pickMeta(res.requirements)
    const { case_id } = await saveCase({ plan_text: res.plan, metadata: meta })
    toast('success', `已保存到案例库：${clipId(case_id)}`)
  } catch (e) {
    toast('error', `保存失败：${e?.message || e}`)
  } finally {
    saving.value = false
  }
}

function onNotify({ type, message }) {
  toast(type, message)
}

onBeforeUnmount(() => planner.cancel())
</script>

<template>
  <div class="app">
    <header class="app-header">
      <div class="app-title">
        <span class="app-logo">🎉</span>
        <div>
          <h1>活动策划多智能体系统</h1>
          <p class="app-subtitle">需求提取 → 场地 / 商家 / 流程并行搜索 → 方案整合</p>
        </div>
      </div>
      <HealthBadge :status="healthStatus" :health="healthData" @refresh="refreshHealth" />
    </header>

    <main class="app-main">
      <PlanningInput
        v-model="requestText"
        :disabled="isStreaming"
        :max-length="INPUT_MAX_LENGTH"
        :api-key-set="healthData?.api_key_set"
        @submit="onSubmit"
        @cancel="planner.cancel"
      />

      <div class="app-columns">
        <PlanViewer
          :status="plannerStatus"
          :plan="planText"
          :result="result"
          :error="errorMsg"
          :saving="saving"
          @save="onSave"
          @notify="onNotify"
        />
        <LogPanel
          :messages="result?.messages || []"
          :errors="result?.errors || []"
          :running="isStreaming"
        />
      </div>
    </main>

    <ToastHost :toasts="toasts" @dismiss="dismiss" />
  </div>
</template>
