import { useState, useEffect, useCallback } from 'react'
import { BookOpen, Search, Loader2, Plus, Pencil, Trash2, Save, X } from 'lucide-react'
import { libraryApi } from '../api/library'
import type { LibEntry } from '../api/library'

type Draft = { id?: string; domain: string; title: string; tags: string; stack: string; when: string; principle: string; exemplar: string; pitfalls: string }
const EMPTY: Draft = { domain: '', title: '', tags: '', stack: '', when: '', principle: '', exemplar: '', pitfalls: '' }

export default function Library() {
  const [domains, setDomains] = useState<string[]>([])
  const [domain, setDomain] = useState('')
  const [entries, setEntries] = useState<LibEntry[]>([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<LibEntry | null>(null)
  const [loading, setLoading] = useState(false)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [saving, setSaving] = useState(false)

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
    try { setEntries(await libraryApi.search(query.trim(), domain || undefined, 12)) } catch { /* ignore */ }
    setLoading(false)
  }

  const open = async (id: string) => {
    setDraft(null)
    try { setSelected(await libraryApi.get(id)) } catch { /* ignore */ }
  }

  const exemplarText = (e: LibEntry) => Array.isArray(e.exemplar) ? e.exemplar.join('\n') : (e.exemplar || '')

  const startEdit = (e: LibEntry) => {
    setDraft({
      id: e.id, domain: e.domain, title: e.title,
      tags: (e.tags || []).join(', '), stack: (e.stack || []).join(', '),
      when: e.when || '', principle: e.principle || '', exemplar: exemplarText(e), pitfalls: e.pitfalls || '',
    })
  }
  const startNew = () => { setSelected(null); setDraft({ ...EMPTY, domain: domain || '' }) }

  const saveDraft = async () => {
    if (!draft || !draft.title.trim() || !draft.domain.trim()) return
    setSaving(true)
    const payload = {
      id: draft.id, domain: draft.domain.trim(), title: draft.title.trim(),
      tags: draft.tags.split(',').map(s => s.trim()).filter(Boolean),
      stack: draft.stack.split(',').map(s => s.trim()).filter(Boolean),
      when: draft.when, principle: draft.principle, exemplar: draft.exemplar, pitfalls: draft.pitfalls,
    }
    try {
      const saved = draft.id ? await libraryApi.update(draft.id, payload) : await libraryApi.create(payload)
      setDraft(null); setSelected(saved); load()
    } catch { /* ignore */ }
    setSaving(false)
  }

  const del = async (e: LibEntry) => {
    if (!confirm(`Delete recipe "${e.title}"?`)) return
    await libraryApi.remove(e.id).catch(() => {})
    setSelected(null); setDraft(null); load()
  }

  const F = ({ label, value, onChange, area }: { label: string; value: string; onChange: (v: string) => void; area?: boolean }) => (
    <div>
      <label className="block text-xs font-mono text-muted uppercase mb-1">{label}</label>
      {area
        ? <textarea value={value} onChange={e => onChange(e.target.value)} rows={label === 'Exemplar' ? 10 : 3}
            className="w-full bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-sm text-slate-200 font-mono" />
        : <input value={value} onChange={e => onChange(e.target.value)}
            className="w-full bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-sm text-slate-200" />}
    </div>
  )

  return (
    <div className="flex-1 overflow-hidden flex">
      <div className="w-[440px] flex-shrink-0 border-r border-surface-700 flex flex-col">
        <div className="px-4 py-3 border-b border-surface-700 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2"><BookOpen size={16} className="text-accent-400" /><span className="text-sm font-semibold text-slate-200">Knowledge Library</span></div>
            <button onClick={startNew} className="flex items-center gap-1 text-xs bg-accent-500/20 border border-accent-500/40 text-accent-300 rounded px-2 py-1 hover:bg-accent-500/30"><Plus size={12} /> New</button>
          </div>
          <p className="text-xs text-muted">Vetted recipes the agents retrieve before they build. Add your own to teach them.</p>
          <div className="flex gap-2">
            <select value={domain} onChange={e => setDomain(e.target.value)} className="bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-xs text-slate-200">
              <option value="">All domains</option>
              {domains.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <div className="flex-1 flex gap-1">
              <input value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') runSearch() }} placeholder="Search recipes…"
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

      <div className="flex-1 overflow-y-auto p-6">
        {draft ? (
          <div className="max-w-3xl space-y-3">
            <div className="flex items-center justify-between">
              <h1 className="text-lg font-semibold text-slate-100">{draft.id ? 'Edit recipe' : 'New recipe'}</h1>
              <div className="flex gap-2">
                <button onClick={() => setDraft(null)} className="flex items-center gap-1 text-xs text-muted border border-surface-600 rounded px-2 py-1"><X size={12} /> Cancel</button>
                <button onClick={saveDraft} disabled={saving || !draft.title.trim() || !draft.domain.trim()} className="flex items-center gap-1 text-xs bg-accent-500 text-white rounded px-3 py-1 disabled:opacity-50">{saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save</button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <F label="Domain" value={draft.domain} onChange={v => setDraft({ ...draft, domain: v })} />
              <F label="Title" value={draft.title} onChange={v => setDraft({ ...draft, title: v })} />
            </div>
            <F label="Tags (comma-separated)" value={draft.tags} onChange={v => setDraft({ ...draft, tags: v })} />
            <F label="Stack (comma-separated)" value={draft.stack} onChange={v => setDraft({ ...draft, stack: v })} />
            <F label="When to use" value={draft.when} onChange={v => setDraft({ ...draft, when: v })} area />
            <F label="Principle" value={draft.principle} onChange={v => setDraft({ ...draft, principle: v })} area />
            <F label="Exemplar" value={draft.exemplar} onChange={v => setDraft({ ...draft, exemplar: v })} area />
            <F label="Pitfalls" value={draft.pitfalls} onChange={v => setDraft({ ...draft, pitfalls: v })} area />
          </div>
        ) : !selected ? (
          <div className="h-full flex items-center justify-center text-muted text-sm">Select a recipe, or click <span className="text-accent-400 mx-1">New</span> to add one.</div>
        ) : (
          <div className="max-w-3xl space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[10px] font-mono uppercase text-accent-400 bg-accent-500/10 px-1.5 py-0.5 rounded">{selected.domain}</span>
                <h1 className="text-xl font-semibold text-slate-100 mt-2">{selected.title}</h1>
              </div>
              <div className="flex gap-2">
                <button onClick={() => startEdit(selected)} className="flex items-center gap-1 text-xs text-muted border border-surface-600 rounded px-2 py-1 hover:text-slate-200"><Pencil size={12} /> Edit</button>
                <button onClick={() => del(selected)} className="flex items-center gap-1 text-xs text-red-400 border border-red-800 rounded px-2 py-1"><Trash2 size={12} /></button>
              </div>
            </div>
            {selected.tags && <div className="flex flex-wrap gap-1">{selected.tags.map(t => <span key={t} className="text-[10px] font-mono text-surface-300 bg-surface-700 px-1.5 py-0.5 rounded">{t}</span>)}</div>}
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
