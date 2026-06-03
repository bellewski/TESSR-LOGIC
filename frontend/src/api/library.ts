import api from './client'

export interface LibEntry {
  id: string; domain: string; title: string
  tags?: string[]; when?: string; stack?: string[]
  principle?: string; exemplar?: string | string[]; pitfalls?: string
}

export const libraryApi = {
  list: (domain?: string) =>
    api.get<{ domains: string[]; entries: LibEntry[] }>('/library', { params: domain ? { domain } : {} }).then(r => r.data),
  search: (q: string, domain?: string, k = 6) =>
    api.get<{ results: LibEntry[] }>('/library/search', { params: { q, domain, k } }).then(r => r.data.results),
  get: (id: string) => api.get<LibEntry>(`/library/${id}`).then(r => r.data),
}
