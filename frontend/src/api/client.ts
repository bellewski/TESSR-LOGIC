import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  // Many endpoints call the local LLM synchronously (Prompt Studio chat, prompt generate,
  // Workshop edits). Those take seconds-to-minutes on local models — 15s aborted them.
  // 2 min covers normal LLM calls; the Workshop edit overrides this to 10 min.
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

export default api
