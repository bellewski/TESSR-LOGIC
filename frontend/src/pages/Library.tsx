import { useState, useEffect, useCallback } from 'react'
import { BookOpen, Search, Loader2 } from 'lucide-react'
import { libraryApi } from '../api/library'
import type { LibEntry } from '../api/library'

export default function Library() {
  const [domains, setDomains] = useState<string[]>([])
  const [domain, setDomain] = useState('')
  const [entries, setEntries] = useState<LibEntry[]>([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<LibEntry | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    libraryApi.list(domain || undefined).then(r => {
      setDomains(r.domains); setEntries(r.entries)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [domain])
  useEffect(() => { load() }, [load])

  const runSearch = async () => {
    if (!query.trim()) { load(); return }
    setLoading(true)
    try { setEntries(await libraryApi.search(query.trim(), domain || undefined, 12)) }
    catch { /* ignore */ }
    setLoading(false)
  }

  const open = async (id: string) => {
    try { setSelected(await libraryApi.get(id)) } catch { /* ignore */ }
  }

  const exemplarText = (e: LibEntry) =>
    Array.isArray(e.exemplar) ? e.exemplar.join('\n') : (e.exemplar || '')

  return (
    <div className="flex-1 overflow-hidden flex">
      {/* list */}
      <div className="w-[440px] flex-shrink-0 border-r border-surface-700 flex flex-col">
        <div className="px-4 py-3 border-b border-surface-700 space-y-2">
          <div className="flex items-center gap-2">
            <BookOpen size={16} className="text-accent-400" />
            <span className="text-sm font-semibold text-slate-200">Knowledge Library</span>
          </div>
          <p className="text-xs text-muted">Vetted cross-domain recipes the agents retrieve before they build.</p>
          <div className="flex gap-2">
            <select value={domain} onChange={e => setDomain(e.target.value)}
              className="bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-xs text-slate-200">
              <option value="">All domains</option>
              {domains.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <div className="flex-1 flex gap-1">
              <input value={query} onChange={e => setQuery(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') runSearch() }}
                placeholder="Search recipes…"
                className="flex-1 bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-xs text-slate-200" />
              <button onClick={runSearch} className="px-2 bg-accent-500/20 border border-accent-500/40 text-accent-300 rounded"><Search size={13} /></button>
            </div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loading && <div className="text-xs text-muted p-2 flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Loading…</div>}
          {entries.map(e => (
            <button key={e.id} onClick={() => open(e.id)}
              className={`w-full text-left rounded px-3 py-2 border ${selected?.id === e.id ? 'border-accent-500 bg-accent-500/10' : 'border-surface-700 hover:bg-surface-700'}`}>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase text-accent-400 bg-accent-500/10 px-1.5 py-0.5 rounded">{e.domain}</span>
                <span className="text-sm text-slate-200 truncate">{e.title}</span>
              </div>
              {e.when && <div className="text-xs text-muted mt-1 truncate">{e.when}</div>}
            </button>
          ))}
          {!loading && entries.length === 0 && <div className="text-xs text-muted p-2">No recipes match.</div>}
        </div>
      </div>

      {/* detail */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selected ? (
          <div className="h-full flex items-center justify-center text-muted text-sm">Select a recipe to view it.</div>
        ) : (
          <div className="max-w-3xl space-y-4">
            <div>
              <span className="text-[10px] font-mono uppercase text-accent-400 bg-accent-500/10 px-1.5 py-0.5 rounded">{selected.domain}</span>
              <h1 className="text-xl font-semibold text-slate-100 mt-2">{selected.title}</h1>
              {selected.tags && <div className="flex flex-wrap gap-1 mt-2">{selected.tags.map(t => <span key={t} className="text-[10px] font-mono text-surface-300 bg-surface-700 px-1.5 py-0.5 rounded">{t}</span>)}</div>}
            </div>
            {selected.when && <div><div className="text-xs font-mono text-muted uppercase">Use when</div><p className="text-sm text-slate-300">{selected.when}</p></div>}
            {selected.principle && <div><div className="text-xs font-mono text-muted uppercase">Principle</div><p className="text-sm text-slate-300">{selected.principle}</p></div>}
            {exemplarText(selected) && <div><div className="text-xs font-mono text-muted uppercase mb-1">Exemplar</div><pre className="text-xs text-teal-300 bg-surface-900 rounded p-3 overflow-x-auto">{exemplarText(selected)}</pre></div>}
            {selected.pitfalls && <div><div className="text-xs font-mono text-muted uppercase">Avoid</div><p className="text-sm text-amber-300/90">{selected.pitfalls}</p></div>}
          </div>
        )}
      </div>
    </div>
  )
}
