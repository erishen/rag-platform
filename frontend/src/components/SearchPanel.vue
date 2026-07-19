<script setup>
import { ref } from 'vue'
import { api } from '../api.js'

const q = ref('')
const topK = ref(4)
const results = ref([])
const loading = ref(false)
const error = ref('')

async function run() {
  if (!q.value.trim() || loading.value) return
  loading.value = true
  error.value = ''
  try {
    results.value = await api.search(q.value.trim(), topK.value)
  } catch (e) {
    error.value = e.message
    results.value = []
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <label>检索词</label>
    <input type="text" v-model="q" placeholder="输入查询，仅检索不调用 LLM"
      @keydown.enter.exact.prevent="run" />

    <label>Top-K</label>
    <input type="text" v-model="topK" style="max-width: 120px" />

    <button class="btn" :disabled="loading || !q.trim()" @click="run">
      {{ loading ? '检索中…' : '检索' }}
    </button>

    <p v-if="error" class="msg err">{{ error }}</p>

    <div v-if="results.length" class="bubble a">
      <div v-for="c in results" :key="c.chunk_id" class="chunk">
        <span class="score">{{ c.score }}</span>{{ c.text }}
      </div>
    </div>
  </div>
</template>
