<script setup>
import { ref } from 'vue'
import { api } from '../api.js'

const title = ref('')
const content = ref('')
const loading = ref(false)
const msg = ref('')
const msgType = ref('ok')

async function submit() {
  if (!title.value.trim() || !content.value.trim() || loading.value) return
  loading.value = true
  msg.value = ''
  try {
    const r = await api.ingest(title.value.trim(), content.value.trim())
    msg.value = `已入库：doc_id=${r.doc_id}，切分 ${r.chunks} 个片段`
    msgType.value = 'ok'
    title.value = ''
    content.value = ''
  } catch (e) {
    msg.value = `入库失败：${e.message}`
    msgType.value = 'err'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <label>标题</label>
    <input type="text" v-model="title" placeholder="文档标题" />

    <label>正文</label>
    <textarea v-model="content" placeholder="粘贴要入库的文档内容，将自动切分并向量化"></textarea>

    <button class="btn" :disabled="loading || !title.trim() || !content.trim()" @click="submit">
      {{ loading ? '入库中…' : '入库' }}
    </button>

    <p v-if="msg" class="msg" :class="msgType">{{ msg }}</p>
  </div>
</template>
