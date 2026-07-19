// 所有请求走 /api 前缀，由 Vite 开发代理转发到后端 :8000。
const BASE = '/api'

async function request(method, path, body) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

export const api = {
  health: () => request('GET', '/health'),
  ingest: (title, content) => request('POST', '/ingest', { title, content }),
  search: (q, topK) => {
    const params = new URLSearchParams({ q })
    if (topK) params.set('top_k', String(topK))
    return request('GET', `/search?${params.toString()}`)
  },
  chat: (question) => request('POST', '/chat', { question }),
  reloadLexicon: () => request('POST', '/lexicon/reload'),
}
