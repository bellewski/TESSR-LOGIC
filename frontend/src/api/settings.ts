import api from './client'
import type { AppSettings } from '../types'

export const settingsApi = {
  get: () => api.get<AppSettings>('/settings').then(r => r.data),
  update: (payload: Partial<AppSettings>) =>
    api.patch<AppSettings>('/settings', payload).then(r => r.data),
}

export const ollamaApi = {
  health: () => api.get<{ status: string; connected: boolean }>('/ollama/health').then(r => r.data),
  models: () => api.get<{ models: string[] }>('/ollama/models').then(r => r.data),
}
