import api from './client'

export interface BrandKit {
  slug: string; name: string; industry: string; tagline: string
  primary: string; accent: string; bg: string; has_logo: boolean
}
export interface OutputPlugin {
  id: string; name: string; icon: string; description: string; supports: string[]
}

export const brandKitsApi = {
  list: () => api.get<{ brand_kits: BrandKit[] }>('/brand-kits').then(r => r.data.brand_kits),
  logoUrl: (slug: string) => `/api/brand-kits/${slug}/logo.svg`,
}

export const pluginsApi = {
  list: () => api.get<{ plugins: OutputPlugin[] }>('/plugins').then(r => r.data.plugins),
  // Runs a plugin and triggers a file download of the returned zip.
  run: async (buildId: string, pluginId: string) => {
    const res = await api.post(`/plugins/${buildId}/run/${pluginId}`, null, { responseType: 'blob', timeout: 120000 })
    const cd: string = res.headers['content-disposition'] || ''
    const m = cd.match(/filename="?([^"]+)"?/)
    const fname = m ? m[1] : `${pluginId}.zip`
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement('a')
    a.href = url; a.download = fname; document.body.appendChild(a); a.click()
    a.remove(); URL.revokeObjectURL(url)
    return fname
  },
}
