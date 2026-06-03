import api from './client'

export interface ConnectorFile { path: string; size: number }
export interface Pattern { title: string; principle: string; snippet?: string; why?: string; tags?: string }
export interface LicenseInfo { spdx: string; risk: 'permissive' | 'copyleft' | 'none' | 'unknown'; note: string }
export interface ConnectorSummary {
  name: string; slug: string; source_url: string; focus?: string
  pattern_count: number; created_at: number; license?: LicenseInfo
}

export const connectorsApi = {
  tree: (repo_url: string) =>
    api.post<{ owner: string; repo: string; branch: string; files: ConnectorFile[]; truncated: boolean; license: LicenseInfo }>(
      '/connectors/github/tree', { repo_url }, { timeout: 60000 }).then(r => r.data),

  extract: (repo_url: string, paths: string[], focus: string) =>
    api.post<{ source: string; patterns: Pattern[] }>(
      '/connectors/github/extract', { repo_url, paths, focus }, { timeout: 600000 }).then(r => r.data),

  save: (name: string, source_url: string, focus: string, patterns: Pattern[], license?: LicenseInfo) =>
    api.post<{ slug: string; saved_patterns: number; memory_seeded: number; memory_active: boolean }>(
      '/connectors/save', { name, source_url, focus, patterns, license }).then(r => r.data),

  list: () => api.get<{ connectors: ConnectorSummary[] }>('/connectors').then(r => r.data),
  remove: (slug: string) => api.delete(`/connectors/${slug}`).then(r => r.data),
}
