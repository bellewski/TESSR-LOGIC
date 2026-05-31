import { useState, useEffect, useCallback } from 'react'
import { Wrench, RefreshCw, Save, Sparkles, FileCode, Eye, Check, X, Loader2 } from 'lucide-react'
import { buildsApi } from '../api/builds'
import type { Build } from '../types'

interface FileEntry { relative_path: string; size_bytes: number }

export default function Workshop() {
  const [builds, setBuilds] = useState<Build[]>([])
  const [buildId, setBuildId] = useState<string>('')
  const [files, setFiles] = useState<FileEntry[]>([])
  const [activePath, setActivePath] = useState<string>('')
  const [content, setContent] = useState<string>('')
  const [dirty, setDirty] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [proposed, setProposed] = useState<string | null>(null)
  const [busy, setBusy] = useState<'idle' | 'editing' | 'saving'>('idle')
  const [toast, setToast] = useState<string>('')

  const flash = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 2500) }

  // Load completed builds
  useEffect(() => {
    buildsApi.list(0, 200).then(({ builds }) => {
      const done = builds.filter(b => b.status === 'completed')
      setBuilds(done)
      if (done.length && !buildId) setBuildId(done[0].id)
    }).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loadFiles = useCallback(async (id: string) => {
    if (!id) return
    try {
      const { files } = await buildsApi.workshopFiles(id)
      setFiles(files)
      setActivePath(''); setContent(''); setProposed(null); setDirty(false)
    } catch { setFiles([]) }
  }, [])

  useEffect(() => { if (buildId) loadFiles(buildId) }, [buildId, loadFiles])

  const openFile = async (path: string) => {
    if (dirty && !confirm('Discard unsaved changes to the current file?')) return
    try {
      const { content } = await buildsApi.workshopReadFile(buildId, path)
      setActivePath(path); setContent(content); setProposed(null); setDirty(false); setInstruction('')
    } catch { flash('Could not open file') }
  }

  const save = async (text: string) => {
    setBusy('saving')
    try {
      await buildsApi.workshopSaveFile(buildId, activePath, text)
      setContent(text); setProposed(null); setDirty(false)
      flash('Saved ✓')
    } catch { flash('Save failed') }
    setBusy('idle')
  }

  const askLLM = async () => {
    if (!activePath || !instruction.trim()) return
    setBusy('editing'); setProposed(null)
    try {
      const { proposed } = await buildsApi.workshopEdit(buildId, activePath, instruction.trim())
      setProposed(proposed)
    } catch (e: any) {
      flash(e?.response?.data?.detail || 'LLM edit failed')
    }
    setBusy('idle')
  }

  const isHtml = activePath.toLowerCase().endsWith('.html')
  const previewSrc = buildId ? `/api/builds/${buildId}/serve/` : ''

  return (
    <div className="flex-1 overflow-hidden flex">
      {/* File list */}
      <div className="w-64 flex-shrink-0 border-r border-surface-700 overflow-y-auto flex flex-col">
        <div className="px-3 py-3 border-b border-surface-700">
          <p className="text-xs font-mono font-semibold text-muted uppercase tracking-wider mb-2">Workshop</p>
          <select
            value={buildId}
            onChange={e => setBuildId(e.target.value)}
            className="w-full bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-xs font-mono text-slate-200"
          >
            {builds.length === 0 && <option value="">No completed builds</option>}
            {builds.map(b => <option key={b.id} value={b.id}>{b.project_name}</option>)}
          </select>
        </div>
        <div className="flex items-center justify-between px-3 py-2 border-b border-surface-700">
          <span className="text-xs text-muted font-mono">{files.length} files</span>
          <button onClick={() => loadFiles(buildId)} className="text-muted hover:text-slate-200"><RefreshCw size={12} /></button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {files.map(f => (
            <button
              key={f.relative_path}
              onClick={() => openFile(f.relative_path)}
              className={`flex items-center gap-2 w-full text-left px-3 py-2 text-xs font-mono border-b border-surface-800 transition-colors ${
                activePath === f.relative_path ? 'bg-surface-700 text-accent-400' : 'text-slate-300 hover:bg-surface-700/50'
              }`}
            >
              <FileCode size={12} className="flex-shrink-0 opacity-60" />
              <span className="truncate">{f.relative_path}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {!activePath ? (
          <div className="flex-1 flex flex-col items-center justify-center text-muted text-sm font-mono">
            <Wrench size={32} className="mb-3 opacity-40" />
            Pick a build, then a file, to make final touches.
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between px-4 py-2 border-b border-surface-700">
              <span className="text-sm font-mono text-slate-200 flex items-center gap-2">
                <FileCode size={14} className="text-accent-400" /> {activePath}
                {dirty && <span className="text-amber-400 text-xs">● unsaved</span>}
              </span>
              <div className="flex items-center gap-2">
                {isHtml && (
                  <a href={previewSrc} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-accent-400 hover:text-accent-300 border border-accent-500/30 px-2 py-1 rounded">
                    <Eye size={12} /> Preview site
                  </a>
                )}
                <button
                  onClick={() => save(content)}
                  disabled={busy !== 'idle' || !dirty}
                  className="flex items-center gap-1 text-xs text-teal-300 border border-teal-700 px-2 py-1 rounded disabled:opacity-40 hover:bg-teal-900/30"
                >
                  {busy === 'saving' ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save
                </button>
              </div>
            </div>

            {/* Code area */}
            <textarea
              value={content}
              onChange={e => { setContent(e.target.value); setDirty(true) }}
              spellCheck={false}
              className="flex-1 bg-surface-900 text-slate-200 font-mono text-xs p-4 resize-none outline-none leading-relaxed"
              style={{ minHeight: 0 }}
            />

            {/* LLM edit bar */}
            <div className="border-t border-surface-700 p-3 space-y-2">
              <div className="flex items-center gap-2">
                <Sparkles size={14} className="text-accent-400 flex-shrink-0" />
                <input
                  value={instruction}
                  onChange={e => setInstruction(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askLLM() } }}
                  placeholder="Tell the LLM what to change… e.g. 'make the header gradient purple-to-pink and add a footer'"
                  className="flex-1 bg-surface-900 border border-surface-600 rounded px-3 py-2 text-xs font-mono text-slate-200"
                />
                <button
                  onClick={askLLM}
                  disabled={busy !== 'idle' || !instruction.trim()}
                  className="flex items-center gap-1 text-xs bg-accent-500/20 text-accent-300 border border-accent-500/40 px-3 py-2 rounded disabled:opacity-40 hover:bg-accent-500/30"
                >
                  {busy === 'editing' ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Ask LLM
                </button>
              </div>

              {proposed !== null && (
                <div className="border border-accent-500/40 rounded bg-surface-800">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-surface-700">
                    <span className="text-xs text-accent-400 font-mono">Proposed change — review before applying</span>
                    <div className="flex items-center gap-2">
                      <button onClick={() => save(proposed)} disabled={busy !== 'idle'}
                        className="flex items-center gap-1 text-xs text-teal-300 border border-teal-700 px-2 py-1 rounded hover:bg-teal-900/30">
                        <Check size={12} /> Apply & Save
                      </button>
                      <button onClick={() => setProposed(null)}
                        className="flex items-center gap-1 text-xs text-muted border border-surface-600 px-2 py-1 rounded hover:text-slate-200">
                        <X size={12} /> Discard
                      </button>
                    </div>
                  </div>
                  <pre className="max-h-60 overflow-auto text-xs font-mono text-slate-300 p-3 whitespace-pre-wrap">{proposed}</pre>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {toast && (
        <div className="fixed bottom-5 right-5 bg-surface-800 border border-accent-500/40 text-slate-200 text-xs font-mono px-4 py-2 rounded shadow-lg">
          {toast}
        </div>
      )}
    </div>
  )
}
