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
  brand_kit?: string
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

  // ── Workshop: post-build editing ──
  workshopFiles: (id: string) =>
    api.get<{ files: { relative_path: string; size_bytes: number }[]; total: number; src_dir: string }>(
      `/builds/${id}/workshop/files`).then(r => r.data),

  workshopReadFile: (id: string, path: string) =>
    api.get<{ path: string; content: string }>(`/builds/${id}/workshop/file`, { params: { path } }).then(r => r.data),

  workshopSaveFile: (id: string, path: string, content: string) =>
    api.put<{ saved: boolean; path: string; size_bytes: number }>(
      `/builds/${id}/workshop/file`, { path, content }).then(r => r.data),

  workshopEdit: (id: string, path: string, instruction: string) =>
    // LLM edits rewrite a whole file — can take 30-90s+ on local models. Override the
    // default 15s client timeout (otherwise the request aborts before the model finishes).
    api.post<{ path: string; original: string; proposed: string; model: string }>(
      `/builds/${id}/workshop/edit`, { path, instruction }, { timeout: 600000 }).then(r => r.data),

  // Conversational project-level assistant: describe a change, the LLM picks files & applies it.
  // Async: the backend runs the edit in the background and returns a job_id immediately, then we
  // poll for the result. This avoids the ~100s Cloudflare tunnel request limit (524) on big redesigns.
  workshopAssist: async (id: string, message: string) => {
    const { job_id } = await api.post<{ job_id: string; status: string }>(
      `/builds/${id}/workshop/assist`, { message }, { timeout: 30000 }).then(r => r.data)
    // Poll up to ~10 minutes.
    for (let i = 0; i < 200; i++) {
      await new Promise(res => setTimeout(res, 3000))
      const job = await api.get<{ status: string; summary: string; changed_files: string[]; applied?: boolean }>(
        `/builds/${id}/workshop/assist/${job_id}`, { timeout: 30000 }).then(r => r.data)
      if (job.status === 'done') return { summary: job.summary, changed_files: job.changed_files, applied: !!job.applied }
      if (job.status === 'error') throw new Error(job.summary || 'Assistant failed')
    }
    throw new Error('Timed out waiting for the assistant to finish')
  },
}
