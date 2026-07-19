<script setup>
import { ref } from 'vue'
import { api } from '../api.js'

const question = ref('')
const log = ref([]) // {role:'q'|'a', text, src, ctx}
const loading = ref(false)
const error = ref('')

async function send() {
  const q = question.value.trim()
  if (!q || loading.value) return
  error.value = ''
  question.value = ''
  log.value.push({ role: 'q', text: q })
  loading.value = true
  try {
    const r = await api.chat(q)
    log.value.push({
      role: 'a',
      text: r.answer,
      src: r.source,
      ctx: r.context || [],
    })
  } catch (e) {
    error.value = e.message
    log.value.push({ role: 'a', text: `请求失败：${e.message}`, src: 'error', ctx: [] })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <label>提问</label>
    <textarea v-model="question" placeholder="输入问题，回车发送（Shift+Enter 换行）"
      @keydown.enter.exact.prevent="send"></textarea>
    <button class="btn" :disabled="loading || !question.trim()" @click="send">
      {{ loading ? '生成中…' : '发送' }}
    </button>

    <p v-if="error" class="msg err">{{ error }}</p>

    <div class="chat-log">
      <div v-for="(m, i) in log" :key="i">
        <div v-if="m.role === 'q'" class="bubble q">{{ m.text }}</div>
        <div v-else class="bubble a">
          {{ m.text }}
          <div class="src" v-if="m.src">来源：{{ m.src }}</div>
          <div class="src" v-if="m.ctx && m.ctx.length">
            召回片段 {{ m.ctx.length }} 条
          </div>
          <div v-for="(c, j) in (m.ctx || [])" :key="j" class="chunk">
            <span class="score">{{ c.score }}</span>{{ c.text }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
