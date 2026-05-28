import api from './client'
import type { Build, BuildEvent, GeneratedFile, Finding } from '../types'

export interface CreateBuildPayload {
  project_name: string
  requirement: string
  stack_target: string
  mode: 'fast' | 'quality'
  project_context_id?: string
  prompt_template_id?: string
  source_dir?: string
  workspace_dir?: string
  output_dir?: string
}

export const buildsApi = {
  create: (payload: CreateBuildPayload) =>
    api.post<Build>('/builds', payload).then(r => r.data),

  list: (skip = 0, limit = 50) =>
    api.get<{ builds: Build[]; total: number }>('/builds', { params: { skip, limit } }).then(r => r.data),

  get: (id: string) =>
    api.get<Build>(`/builds/${id}`).then(r => r.data),

  events: (id: string, skip = 0, limit = 200) =>
    api.get<{ events: BuildEvent[]; total: number }>(`/builds/${id}/events`, { params: { skip, limit } }).then(r => r.data),

  files: (id: string) =>
    api.get<{ files: GeneratedFile[]; total: number }>(`/builds/${id}/files`).then(r => r.data),

  findings: (id: string) =>
    api.get<{ findings: Finding[]; total: number }>(`/builds/${id}/findings`).then(r => r.data),

  fileContent: (path: string) =>
    api.get<string>('/files/content', { params: { path }, responseType: 'text' }).then(r => r.data),

  rerun: (id: string) =>
    api.post<Build>(`/builds/${id}/rerun`).then(r => r.data),

  cancel: (id: string) =>
    api.post<Build>(`/builds/${id}/cancel`).then(r => r.data),

  openFolder: (id: string) =>
    api.post<{ opened: boolean; path: string }>(`/builds/${id}/open-folder`).then(r => r.data),

  deleteBuild: (id: string) =>
    api.delete<{ deleted: boolean; id: string }>(`/builds/${id}`).then(r => r.data),
}
