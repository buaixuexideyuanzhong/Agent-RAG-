<script setup>
import { ref, computed } from 'vue'
import { EXAMPLE_REQUESTS, INPUT_MAX_LENGTH } from '../constants'

const props = defineProps({
  modelValue: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  maxLength: { type: Number, default: INPUT_MAX_LENGTH },
  apiKeySet: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue', 'submit', 'cancel'])

const hint = ref('')
const overflow = computed(() => props.modelValue.length > props.maxLength)

const canSubmit = computed(() => {
  const t = props.modelValue.trim()
  return t.length > 0 && t.length <= props.maxLength && !props.disabled
})

function onInput(e) {
  hint.value = ''
  emit('update:modelValue', e.target.value)
}

function submit() {
  const t = props.modelValue.trim()
  if (!t) {
    hint.value = '请输入活动需求'
    return
  }
  if (t.length > props.maxLength) {
    hint.value = `需求描述不能超过 ${props.maxLength} 字`
    return
  }
  emit('submit', t)
}
</script>

<template>
  <section class="planning-input card">
    <textarea
      :value="modelValue"
      :disabled="disabled"
      :maxlength="maxLength"
      rows="4"
      placeholder="描述您的活动需求，例如：帮我策划一个500人的公司年会，预算20万，地点在北京朝阳…"
      @input="onInput"
    />
    <p v-if="!apiKeySet" class="api-warning">
      ⚠️ 后端未配置 LLM_API_KEY，策划接口将不可用（见 /api/v1/health）
    </p>
    <div class="input-meta">
      <div class="input-tools">
        <button
          v-if="!disabled"
          class="btn btn-primary"
          :disabled="!canSubmit"
          @click="submit"
        >
          开始策划
        </button>
        <button v-else class="btn btn-danger" @click="emit('cancel')">中止</button>
      </div>
      <div class="input-extra">
        <div class="examples">
          <span class="label">示例：</span>
          <button
            v-for="(ex, i) in EXAMPLE_REQUESTS"
            :key="i"
            class="example-chip"
            :disabled="disabled"
            @click="emit('update:modelValue', ex)"
          >
            示例{{ i + 1 }}
          </button>
        </div>
        <span class="char-count" :class="{ overflow }">
          {{ modelValue.length }}/{{ maxLength }}
        </span>
      </div>
    </div>
    <p v-if="hint" class="input-hint">{{ hint }}</p>
  </section>
</template>
