import { useState, useEffect } from 'react'
import { Boxes, Archive, Box, Globe, Loader2, Download, Plug } from 'lucide-react'
import { pluginsApi } from '../api/meta'
import type { OutputPlugin } from '../api/meta'
import { buildsApi } from '../api/builds'
import type { Build } from '../types'

const ICONS: Record<string, typeof Archive> = { archive: Archive, box: Box, globe: Globe }

export default function Plugins() {
  const [plugins, setPlugins] = useState<OutputPlugin[]>([])
  const [builds, setBuilds] = useState<Build[]>([])
  const [buildId, setBuildId] = useState('')
  const [running, setRunning] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    pluginsApi.list().then(setPlugins).catch(() => {})
    buildsApi.list(0, 200).then(({ builds }) => {
      const done = builds.filter(b => b.status === 'completed' || b.status === 'failed')
      setBuilds(done)
      if (done.length) setBuildId(done[0].id)
    }).catch(() => {})
  }, [])

  const run = async (pluginId: string) => {
    if (!buildId) { setErr('Pick a build first.'); return }
    setErr(''); setMsg(''); setRunning(pluginId)
    try {
      const fname = await pluginsApi.run(buildId, pluginId)
      setMsg(`Generated ${fname} — download started.`)
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Plugin failed')
    }
    setRunning('')
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-200 flex items-center gap-2">
          <Plug size={18} className="text-accent-400" /> Output &amp; Deploy Plugins
        </h1>
        <p className="text-xs text-muted mt-1 max-w-3xl">
          Pluggable targets for a finished build. Pick a completed build and run a plugin to
          package or containerize it. Runs fully offline.
        </p>
      </div>

      <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 flex items-center gap-3">
        <Boxes size={16} className="text-muted" />
        <label className="text-xs text-muted">Target build</label>
        <select value={buildId} onChange={e => setBuildId(e.target.value)}
          className="flex-1 bg-surface-900 border border-surface-600 rounded px-2 py-2 text-sm text-slate-200 font-mono">
          {builds.length === 0 && <option value="">No completed builds yet</option>}
          {builds.map(b => <option key={b.id} value={b.id}>{b.project_name} · {b.status}</option>)}
        </select>
      </div>

      {err && <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">{err}</div>}
      {msg && <div className="text-sm text-teal-400 bg-teal-900/20 border border-teal-800 rounded px-3 py-2">{msg}</div>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {plugins.map(p => {
          const Icon = ICONS[p.icon] || Archive
          return (
            <div key={p.id} className="bg-surface-800 border border-surface-600 rounded-lg p-4 flex flex-col">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-9 h-9 rounded-lg bg-accent-500/15 flex items-center justify-center text-accent-400"><Icon size={18} /></span>
                <span className="text-sm font-semibold text-slate-200">{p.name}</span>
              </div>
              <p className="text-xs text-muted flex-1">{p.description}</p>
              <div className="flex items-center gap-1 mt-2 mb-3 flex-wrap">
                {p.supports.map(s => <span key={s} className="text-[10px] font-mono text-surface-400 bg-surface-700 px-1.5 py-0.5 rounded">{s}</span>)}
              </div>
              <button onClick={() => run(p.id)} disabled={!buildId || running !== ''}
                className="flex items-center justify-center gap-1.5 px-3 py-2 text-sm bg-accent-500 hover:bg-accent-400 disabled:opacity-50 text-white rounded">
                {running === p.id ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Run
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
