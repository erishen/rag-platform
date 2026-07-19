<script setup>
import { ref, onMounted } from 'vue'
import { api } from './api.js'
import ChatPanel from './components/ChatPanel.vue'
import IngestPanel from './components/IngestPanel.vue'
import SearchPanel from './components/SearchPanel.vue'

const tabs = [
  { key: 'chat', label: '对话' },
  { key: 'ingest', label: '入库' },
  { key: 'search', label: '检索' },
]
const active = ref('chat')

const health = ref({ state: 'pending', llm: false })

async function probeHealth() {
  try {
    const r = await api.health()
    health.value = { state: 'on', llm: !!r.llm_configured }
  } catch {
    health.value = { state: 'err', llm: false }
  }
}

onMounted(probeHealth)
</script>

<template>
  <div>
    <div class="header">
      <h1>rag-platform</h1>
      <div class="status">
        <span
          class="dot"
          :class="health.state === 'on' ? 'on' : health.state === 'err' ? 'err' : 'off'"
        ></span>
        <span v-if="health.state === 'on'">
          后端在线{{ health.llm ? ' · LLM 已配置' : ' · LLM 未配置' }}
        </span>
        <span v-else-if="health.state === 'err'">后端未连接（:8000）</span>
        <span v-else>检测中…</span>
      </div>
    </div>

    <div class="tabs">
      <button
        v-for="t in tabs"
        :key="t.key"
        :class="{ active: active === t.key }"
        @click="active = t.key"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="panel">
      <ChatPanel v-if="active === 'chat'" @llm-changed="probeHealth" />
      <IngestPanel v-else-if="active === 'ingest'" />
      <SearchPanel v-else-if="active === 'search'" />
    </div>
  </div>
</template>
