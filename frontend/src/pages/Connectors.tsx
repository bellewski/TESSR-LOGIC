import { useState, useEffect, useCallback } from 'react'
import { Github, Loader2, Search, CheckCircle2, Save, Trash2, Sparkles, Database, AlertCircle } from 'lucide-react'
import { connectorsApi } from '../api/connectors'
import type { ConnectorFile, Pattern, ConnectorSummary, LicenseInfo } from '../api/connectors'

const LICENSE_STYLE: Record<string, string> = {
  permissive: 'text-teal-400 bg-teal-900/20 border-teal-800',
  copyleft: 'text-amber-400 bg-amber-900/20 border-amber-800',
  none: 'text-red-400 bg-red-900/20 border-red-800',
  unknown: 'text-amber-400 bg-amber-900/20 border-amber-800',
}

export default function Connectors() {
  const [repoUrl, setRepoUrl] = useState('')
  const [focus, setFocus] = useState('')
  const [files, setFiles] = useState<ConnectorFile[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [patterns, setPatterns] = useState<Pattern[]>([])
  const [approved, setApproved] = useState<Set<number>>(new Set())
  const [name, setName] = useState('')
  const [busy, setBusy] = useState<'' | 'tree' | 'extract' | 'save'>('')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState<ConnectorSummary[]>([])
  const [notice, setNotice] = useState('')
  const [license, setLicense] = useState<LicenseInfo | null>(null)

  const loadSaved = useCallback(() => {
    connectorsApi.list().then(r => setSaved(r.connectors)).catch(() => {})
  }, [])
  useEffect(() => { loadSaved() }, [loadSaved])

  const fetchTree = async () => {
    setError(''); setNotice(''); setPatterns([]); setFiles([]); setSelected(new Set())
    setBusy('tree')
    try {
      const r = await connectorsApi.tree(repoUrl)
      setFiles(r.files)
      setLicense(r.license || null)
      if (!name) setName(`${r.repo} patterns`)
      if (r.files.length === 0) setError('No code files found in that repo.')
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to fetch repo')
    }
    setBusy('')
  }

  const toggleFile = (p: string) => setSelected(s => {
    const n = new Set(s); n.has(p) ? n.delete(p) : n.add(p); return n
  })

  const extract = async () => {
    if (selected.size === 0) { setError('Select at least one file to learn from.'); return }
    setError(''); setNotice(''); setBusy('extract')
    try {
      const r = await connectorsApi.extract(repoUrl, [...selected], focus)
      setPatterns(r.patterns)
      setApproved(new Set(r.patterns.map((_, i) => i)))  // pre-approve all; user unchecks the bad ones
      if (r.patterns.length === 0) setError('No patterns extracted — try different/fewer files.')
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Extraction failed')
    }
    setBusy('')
  }

  const toggleApprove = (i: number) => setApproved(s => {
    const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n
  })

  const save = async () => {
    const keep = patterns.filter((_, i) => approved.has(i))
    if (keep.length === 0) { setError('Approve at least one pattern to save.'); return }
    if (!name.trim()) { setError('Give this connector a name.'); return }
    setError(''); setBusy('save')
    try {
      const r = await connectorsApi.save(name.trim(), repoUrl, focus, keep, license || undefined)
      setNotice(`Saved "${name}" — ${r.saved_patterns} pattern(s). ` +
        (r.memory_active ? `${r.memory_seeded} fed into the offline learning memory.` :
          'Memory layer is OFF (pull the nomic-embed-text model to enable learning).'))
      setPatterns([]); setApproved(new Set()); setFiles([]); setSelected(new Set()); setLicense(null)
      loadSaved()
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Save failed')
    }
    setBusy('')
  }

  const del = async (slug: string) => {
    if (!confirm('Delete this connector?')) return
    await connectorsApi.remove(slug).catch(() => {})
    loadSaved()
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-200 flex items-center gap-2">
          <Github size={18} className="text-accent-400" /> Connectors — Learn from GitHub
        </h1>
        <p className="text-xs text-muted mt-1 max-w-3xl">
          Online ingest → offline build. Pull a public repo, let the LLM extract reusable code
          <em> patterns</em> (not copies), verify them, and save them as a connector that feeds TESSR's
          offline learning memory. Builds stay air-gapped — this tab is the only thing that touches the network.
        </p>
      </div>

      {/* Step 1: repo */}
      <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-3">
        <div className="text-xs font-mono text-muted uppercase tracking-wider">1 · Source repo</div>
        <div className="flex gap-2">
          <input value={repoUrl} onChange={e => setRepoUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            className="flex-1 bg-surface-900 border border-surface-600 rounded px-3 py-2 text-sm text-slate-200" />
          <button onClick={fetchTree} disabled={!repoUrl || busy !== ''}
            className="flex items-center gap-1.5 px-3 py-2 text-sm bg-accent-500 hover:bg-accent-400 disabled:opacity-50 text-white rounded">
            {busy === 'tree' ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />} Fetch
          </button>
        </div>
        <input value={focus} onChange={e => setFocus(e.target.value)}
          placeholder="Optional focus — e.g. 'auth flow', 'chart rendering', 'form validation'"
          className="w-full bg-surface-900 border border-surface-600 rounded px-3 py-2 text-xs text-slate-300" />
      </div>

      {error && <div className="flex items-center gap-2 text-sm text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2"><AlertCircle size={14} />{error}</div>}
      {notice && <div className="flex items-center gap-2 text-sm text-teal-400 bg-teal-900/20 border border-teal-800 rounded px-3 py-2"><CheckCircle2 size={14} />{notice}</div>}
      {license && (
        <div className={`flex items-start gap-2 text-sm border rounded px-3 py-2 ${LICENSE_STYLE[license.risk] || LICENSE_STYLE.unknown}`}>
          <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
          <span><strong>License: {license.spdx}</strong> ({license.risk}) — {license.note}</span>
        </div>
      )}

      {/* Step 2: pick files */}
      {files.length > 0 && (
        <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs font-mono text-muted uppercase tracking-wider">2 · Pick files to learn from ({selected.size} selected)</div>
            <button onClick={extract} disabled={selected.size === 0 || busy !== ''}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-accent-500/20 text-accent-300 border border-accent-500/40 rounded disabled:opacity-50 hover:bg-accent-500/30">
              {busy === 'extract' ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} Extract patterns
            </button>
          </div>
          <div className="max-h-56 overflow-y-auto space-y-0.5">
            {files.map(f => (
              <label key={f.path} className="flex items-center gap-2 text-xs font-mono text-slate-300 px-2 py-1 rounded hover:bg-surface-700 cursor-pointer">
                <input type="checkbox" checked={selected.has(f.path)} onChange={() => toggleFile(f.path)} />
                <span className="truncate">{f.path}</span>
                <span className="text-surface-500 ml-auto">{(f.size / 1024).toFixed(1)}k</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Step 3: verify patterns */}
      {patterns.length > 0 && (
        <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-3">
          <div className="text-xs font-mono text-muted uppercase tracking-wider">3 · Verify patterns ({approved.size} approved)</div>
          <div className="space-y-2">
            {patterns.map((p, i) => (
              <div key={i} className={`border rounded p-3 ${approved.has(i) ? 'border-accent-500/40 bg-accent-500/5' : 'border-surface-600 opacity-60'}`}>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input type="checkbox" checked={approved.has(i)} onChange={() => toggleApprove(i)} className="mt-1" />
                  <div className="flex-1">
                    <div className="text-sm font-semibold text-slate-200">{p.title}</div>
                    <div className="text-xs text-slate-300 mt-1">{p.principle}</div>
                    {p.why && <div className="text-xs text-muted mt-1"><span className="text-accent-400">Why:</span> {p.why}</div>}
                    {p.snippet && <pre className="text-[11px] text-teal-300 bg-surface-900 rounded p-2 mt-1.5 overflow-x-auto">{p.snippet}</pre>}
                  </div>
                </label>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 pt-1">
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Connector name"
              className="flex-1 bg-surface-900 border border-surface-600 rounded px-3 py-2 text-sm text-slate-200" />
            <button onClick={save} disabled={busy !== '' || approved.size === 0}
              className="flex items-center gap-1.5 px-3 py-2 text-sm bg-accent-500 hover:bg-accent-400 disabled:opacity-50 text-white rounded">
              {busy === 'save' ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save connector
            </button>
          </div>
        </div>
      )}

      {/* Saved connectors */}
      <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-2">
        <div className="text-xs font-mono text-muted uppercase tracking-wider flex items-center gap-1.5"><Database size={13} /> Saved connectors ({saved.length})</div>
        {saved.length === 0 && <p className="text-xs text-muted">None yet — ingest a repo above.</p>}
        {saved.map(c => (
          <div key={c.slug} className="flex items-center gap-2 text-sm border-b border-surface-700 py-2 last:border-0">
            <div className="flex-1 min-w-0">
              <span className="text-slate-200 font-medium">{c.name}</span>
              {c.license?.spdx && c.license.spdx !== 'none' && (
                <span className="text-[10px] font-mono ml-2 px-1.5 py-0.5 rounded bg-surface-700 text-surface-300">{c.license.spdx}</span>
              )}
              <span className="text-xs text-muted ml-2">{c.pattern_count} patterns · {c.source_url}</span>
            </div>
            <button onClick={() => del(c.slug)} className="text-red-500 hover:text-red-400"><Trash2 size={13} /></button>
          </div>
        ))}
      </div>
    </div>
  )
}
