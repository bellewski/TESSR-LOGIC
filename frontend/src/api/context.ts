import api from './client'
import type { ProjectContext, ScanResult, FileManifestEntry, BuildDirectoryConfig } from '../types'

export const contextApi = {
  list: () =>
    api.get<ProjectContext[]>('/contexts').then(r => r.data),

  get: (id: string) =>
    api.get<ProjectContext>(`/contexts/${id}`).then(r => r.data),

  create: (payload: { name: string; source_dir?: string; workspace_dir?: string; output_dir?: string }) =>
    api.post<ProjectContext>('/contexts', payload).then(r => r.data),

  update: (id: string, payload: Partial<ProjectContext>) =>
    api.patch<ProjectContext>(`/contexts/${id}`, payload).then(r => r.data),

  delete: (id: string) =>
    api.delete(`/contexts/${id}`),

  scan: (contextId: string, sourceDir: string) =>
    api.post<ScanResult>(`/contexts/${contextId}/scan`, { source_dir: sourceDir }).then(r => r.data),

  quickScan: (sourceDir: string) =>
    api.post<ScanResult>('/contexts/scan', { source_dir: sourceDir }).then(r => r.data),

  getManifest: (contextId: string) =>
    api.get<FileManifestEntry[]>(`/contexts/${contextId}/manifest`).then(r => r.data),

  getBuildDirectories: (buildId: string) =>
    api.get<BuildDirectoryConfig>(`/builds/${buildId}/directories`).then(r => r.data),
}
