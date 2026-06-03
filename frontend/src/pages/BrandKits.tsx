import { useState, useEffect, useCallback } from 'react'
import { Palette, Plus, Trash2, Save, X, Loader2 } from 'lucide-react'
import { brandKitsApi } from '../api/meta'
import type { BrandKit } from '../api/meta'

const COLOR_FIELDS: { key: string; label: string; def: string }[] = [
  { key: 'bg', label: 'Background', def: '#0b0e1a' },
  { key: 'surface', label: 'Surface', def: '#1b2238' },
  { key: 'primary', label: 'Primary', def: '#6366f1' },
  { key: 'accent', label: 'Accent', def: '#8b5cf6' },
  { key: 'text', label: 'Text', def: '#e5e7eb' },
]

const BLANK = () => ({
  name: '', industry: '', tagline: '', tone: '', audience: '', font_stack: '', aesthetic: '', logo_svg: '',
  colors: Object.fromEntries(COLOR_FIELDS.map(f => [f.key, f.def])) as Record<string, string>,
})

export default function BrandKits() {
  const [kits, setKits] = useState<BrandKit[]>([])
  const [draft, setDraft] = useState<ReturnType<typeof BLANK> | null>(null)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(() => { brandKitsApi.list().then(setKits).catch(() => {}) }, [])
  useEffect(() => { load() }, [load])

  const save = async () => {
    if (!draft || !draft.name.trim()) { setErr('Name is required.'); return }
    setSaving(true); setErr('')
    try {
      await brandKitsApi.create({
        name: draft.name.trim(), industry: draft.industry, tagline: draft.tagline,
        voice: { tone: draft.tone, audience: draft.audience },
        colors: draft.colors, font_stack: draft.font_stack,
        aesthetic: draft.aesthetic.split(',').map(s => s.trim()).filter(Boolean),
        logo_svg: draft.logo_svg.trim() || undefined,
      })
      setDraft(null); load()
    } catch (e: any) { setErr(e?.response?.data?.detail || e?.message || 'Save failed') }
    setSaving(false)
  }

  const del = async (slug: string) => {
    if (!confirm('Delete this brand kit?')) return
    await brandKitsApi.remove(slug).catch(() => {})
    load()
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-slate-200 flex items-center gap-2"><Palette size={18} className="text-accent-400" /> Brand Kits</h1>
          <p className="text-xs text-muted mt-1">Define your brand once — colors, fonts, voice, logo. Builds can apply it. Fully offline.</p>
        </div>
        {!draft && <button onClick={() => setDraft(BLANK())} className="flex items-center gap-1.5 px-3 py-2 text-sm bg-accent-500 hover:bg-accent-400 text-white rounded"><Plus size={14} /> New brand kit</button>}
      </div>

      {err && <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">{err}</div>}

      {draft && (
        <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-3 max-w-3xl">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-200">New brand kit</span>
            <div className="flex gap-2">
              <button onClick={() => setDraft(null)} className="flex items-center gap-1 text-xs text-muted border border-surface-600 rounded px-2 py-1"><X size={12} /> Cancel</button>
              <button onClick={save} disabled={saving || !draft.name.trim()} className="flex items-center gap-1 text-xs bg-accent-500 text-white rounded px-3 py-1 disabled:opacity-50">{saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save</button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {([['name', 'Brand name'], ['industry', 'Industry'], ['tagline', 'Tagline'], ['font_stack', 'Font stack (optional)'], ['tone', 'Voice tone'], ['audience', 'Audience']] as const).map(([k, label]) => (
              <div key={k}>
                <label className="block text-xs font-mono text-muted uppercase mb-1">{label}</label>
                <input value={(draft as any)[k]} onChange={e => setDraft({ ...draft, [k]: e.target.value })}
                  className="w-full bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-sm text-slate-200" />
              </div>
            ))}
          </div>
          <div>
            <label className="block text-xs font-mono text-muted uppercase mb-1">Colors</label>
            <div className="flex flex-wrap gap-3">
              {COLOR_FIELDS.map(f => (
                <div key={f.key} className="flex items-center gap-1.5">
                  <input type="color" value={draft.colors[f.key]} onChange={e => setDraft({ ...draft, colors: { ...draft.colors, [f.key]: e.target.value } })} className="w-8 h-8 rounded bg-transparent border border-surface-600" />
                  <span className="text-xs text-muted">{f.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs font-mono text-muted uppercase mb-1">Aesthetic keywords (comma-separated)</label>
            <input value={draft.aesthetic} onChange={e => setDraft({ ...draft, aesthetic: e.target.value })} placeholder="glassmorphism, bold type, minimal"
              className="w-full bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-sm text-slate-200" />
          </div>
          <div>
            <label className="block text-xs font-mono text-muted uppercase mb-1">Logo — paste inline SVG (optional, stays offline)</label>
            <textarea value={draft.logo_svg} onChange={e => setDraft({ ...draft, logo_svg: e.target.value })} rows={4} placeholder="<svg ...>…</svg>"
              className="w-full bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-xs font-mono text-slate-200" />
          </div>
        </div>
      )}

      {/* existing kits */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {kits.map(k => (
          <div key={k.slug} className="bg-surface-800 border border-surface-600 rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-sm font-semibold text-slate-200">{k.name}</div>
                <div className="text-xs text-muted">{k.industry}</div>
              </div>
              <button onClick={() => del(k.slug)} className="text-red-500 hover:text-red-400" title="Delete"><Trash2 size={13} /></button>
            </div>
            {k.tagline && <p className="text-xs text-slate-400 mt-2 italic">"{k.tagline}"</p>}
            <div className="flex items-center gap-1 mt-3">
              {[k.bg, k.primary, k.accent].filter(Boolean).map((c, i) => (
                <span key={i} className="w-6 h-6 rounded border border-surface-600" style={{ background: c }} />
              ))}
              {k.has_logo && <img src={brandKitsApi.logoUrl(k.slug)} alt={k.name} className="h-6 ml-2" style={{ maxWidth: 120 }} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
