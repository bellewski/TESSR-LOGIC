import { useState, useEffect } from 'react'
import { FolderOpen, ScanLine, Plus, Trash2, Loader2, RefreshCw, FileText, ChevronRight } from 'lucide-react'
import { contextApi } from '../api/context'
import type { ProjectContext as ProjectContextType, ScanResult, FileManifestEntry } from '../types'

function DirInput({ label, value, onChange }: {
  label: string; value: string; onChange: (v: string) => void
}) {
  return (
    <div>
      <label className="block text-xs text-muted mb-1">{label}</label>
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder="C:\path\to\folder"
          className="flex-1 bg-surface-700 border border-surface-500 rounded px-3 py-1.5 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500 font-mono"
        />
        <FolderOpen size={14} className="self-center text-muted flex-shrink-0" />
      </div>
    </div>
  )
}

function StackBadge({ stack }: { stack: string }) {
  const COLORS: Record<string, string> = {
    'Node.js': 'bg-green-900/40 text-green-300 border-green-800',
    'Python': 'bg-blue-900/40 text-blue-300 border-blue-800',
    'TypeScript': 'bg-cyan-900/40 text-cyan-300 border-cyan-800',
    'Vite': 'bg-purple-900/40 text-purple-300 border-purple-800',
    'TailwindCSS': 'bg-teal-900/40 text-teal-300 border-teal-800',
    'Docker': 'bg-sky-900/40 text-sky-300 border-sky-800',
    'Next.js': 'bg-slate-600/40 text-slate-200 border-slate-500',
    'Go': 'bg-sky-900/40 text-sky-200 border-sky-700',
    'Rust': 'bg-orange-900/40 text-orange-300 border-orange-700',
  }
  const cls = COLORS[stack] || 'bg-surface-700 text-slate-300 border-surface-500'
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded border ${cls}`}>{stack}</span>
  )
}

export default function ProjectContext() {
  const [contexts, setContexts] = useState<ProjectContextType[]>([])
  const [selected, setSelected] = useState<ProjectContextType | null>(null)
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [manifest, setManifest] = useState<FileManifestEntry[]>([])
  const [scanning, setScanning] = useState(false)
  const [creating, setCreating] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Edit state for selected context dirs
  const [sourceDir, setSourceDir] = useState('')
  const [workspaceDir, setWorkspaceDir] = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [ctxName, setCtxName] = useState('')

  const loadContexts = () =>
    contextApi.list().then(list => {
      setContexts(list)
      setLoading(false)
    }).catch(() => setLoading(false))

  useEffect(() => { loadContexts() }, [])

  const selectContext = async (ctx: ProjectContextType) => {
    setSelected(ctx)
    setSourceDir(ctx.source_dir || '')
    setWorkspaceDir(ctx.workspace_dir || '')
    setOutputDir(ctx.output_dir || '')
    setScanResult(null)
    setManifest([])
    if (ctx.last_scanned_at) {
      contextApi.getManifest(ctx.id).then(setManifest).catch(() => {})
    }
  }

  const handleCreate = async () => {
    if (!ctxName.trim()) return
    setCreating(true)
    setError(null)
    try {
      const ctx = await contextApi.create({ name: ctxName.trim() })
      await loadContexts()
      setCtxName('')
      selectContext(ctx)
    } catch { setError('Create failed') }
    finally { setCreating(false) }
  }

  const handleSave = async () => {
    if (!selected) return
    setError(null)
    try {
      const updated = await contextApi.update(selected.id, {
        source_dir: sourceDir || null,
        workspace_dir: workspaceDir || null,
        output_dir: outputDir || null,
      } as Partial<ProjectContextType>)
      setSelected(updated)
      await loadContexts()
    } catch { setError('Save failed') }
  }

  const handleScan = async () => {
    if (!selected || !sourceDir.trim()) {
      setError('Set a source directory first')
      return
    }
    setScanning(true)
    setError(null)
    try {
      // Save dirs first
      await contextApi.update(selected.id, {
        source_dir: sourceDir || null,
        workspace_dir: workspaceDir || null,
        output_dir: outputDir || null,
      } as Partial<ProjectContextType>)
      const result = await contextApi.scan(selected.id, sourceDir.trim())
      setScanResult(result)
      const mf = await contextApi.getManifest(selected.id)
      setManifest(mf)
      await loadContexts()
      // Refresh selected
      const refreshed = await contextApi.get(selected.id)
      setSelected(refreshed)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Scan failed — check the path')
    } finally {
      setScanning(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this context?')) return
    try {
      await contextApi.delete(id)
      if (selected?.id === id) { setSelected(null); setScanResult(null) }
      await loadContexts()
    } catch { setError('Delete failed') }
  }

  const keyFiles = selected?.detected_files
    ? (() => { try { return JSON.parse(selected.detected_files!) as string[] } catch { return [] } })()
    : (scanResult?.key_files ?? [])

  const stackList = selected?.detected_stack
    ? (() => { try { return JSON.parse(selected.detected_stack!) as string[] } catch { return [] } })()
    : (scanResult?.detected_stack ?? [])

  return (
    <div className="flex-1 overflow-hidden flex">
      {/* Sidebar: context list */}
      <div className="w-56 flex-shrink-0 border-r border-surface-700 flex flex-col overflow-hidden">
        <div className="px-3 py-3 border-b border-surface-700">
          <p className="text-xs font-mono font-semibold text-muted uppercase tracking-wider mb-2">Project Contexts</p>
          <div className="flex gap-1.5">
            <input
              value={ctxName}
              onChange={e => setCtxName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCreate() }}
              placeholder="New context name"
              className="flex-1 min-w-0 bg-surface-700 border border-surface-500 rounded px-2 py-1 text-xs text-slate-200 placeholder-muted focus:outline-none"
            />
            <button
              onClick={handleCreate}
              disabled={creating || !ctxName.trim()}
              className="p-1 bg-accent-500 hover:bg-accent-400 disabled:opacity-40 text-white rounded transition-colors"
            >
              {creating ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading && <p className="text-muted text-xs p-3 font-mono italic">Loading…</p>}
          {contexts.map(ctx => (
            <div
              key={ctx.id}
              onClick={() => selectContext(ctx)}
              className={`flex items-center justify-between px-3 py-2.5 cursor-pointer group transition-colors ${
                selected?.id === ctx.id ? 'bg-surface-700 text-slate-200' : 'hover:bg-surface-700/50 text-slate-400'
              }`}
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate">{ctx.name}</p>
                {ctx.inferred_project_type && (
                  <p className="text-xs text-muted truncate">{ctx.inferred_project_type}</p>
                )}
              </div>
              <button
                onClick={e => { e.stopPropagation(); handleDelete(ctx.id) }}
                className="opacity-0 group-hover:opacity-100 text-muted hover:text-red-400 transition-all ml-1 flex-shrink-0"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main panel */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {!selected ? (
          <div className="flex flex-col items-center justify-center h-64 text-muted text-sm font-mono">
            <FolderOpen size={32} className="mb-3 opacity-40" />
            Select or create a project context to get started.
          </div>
        ) : (
          <>
            {error && (
              <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>
            )}

            {/* Directory config */}
            <div className="bg-surface-800 border border-surface-600 rounded-lg p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-200">{selected.name}</h2>
                <button
                  onClick={handleSave}
                  className="text-xs px-3 py-1.5 border border-surface-500 rounded text-muted hover:text-slate-200 transition-colors"
                >
                  Save dirs
                </button>
              </div>
              <div className="grid grid-cols-1 gap-3">
                <DirInput label="Source Directory" value={sourceDir} onChange={setSourceDir} />
                <DirInput label="Workspace Directory" value={workspaceDir} onChange={setWorkspaceDir} />
                <DirInput label="Output Directory (final deliverables)" value={outputDir} onChange={setOutputDir} />
              </div>
              <button
                onClick={handleScan}
                disabled={scanning || !sourceDir.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-accent-500 hover:bg-accent-400 disabled:opacity-40 text-white text-sm font-medium rounded transition-colors"
              >
                {scanning ? <Loader2 size={14} className="animate-spin" /> : <ScanLine size={14} />}
                {scanning ? 'Scanning…' : 'Scan Source Folder'}
              </button>
            </div>

            {/* Detected stack + summary */}
            {(stackList.length > 0 || selected.context_summary) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
                  <p className="text-xs font-mono text-muted uppercase tracking-wider mb-3">Detected Stack</p>
                  {selected.inferred_project_type && (
                    <p className="text-sm text-slate-300 mb-2 font-semibold">{selected.inferred_project_type}</p>
                  )}
                  <div className="flex flex-wrap gap-1.5">
                    {stackList.map(s => <StackBadge key={s} stack={s} />)}
                    {stackList.length === 0 && <span className="text-muted text-xs italic">Not scanned yet</span>}
                  </div>
                  {selected.total_files_scanned > 0 && (
                    <p className="text-xs text-muted mt-3">{selected.total_files_scanned} files scanned</p>
                  )}
                </div>
                <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
                  <p className="text-xs font-mono text-muted uppercase tracking-wider mb-3">Context Summary</p>
                  <p className="text-xs text-slate-300 leading-5">
                    {selected.context_summary || 'No summary yet — run a scan.'}
                  </p>
                </div>
              </div>
            )}

            {/* Key files */}
            {keyFiles.length > 0 && (
              <div className="bg-surface-800 border border-surface-600 rounded-lg overflow-hidden">
                <div className="px-3 py-2 border-b border-surface-600">
                  <p className="text-xs font-mono text-muted uppercase tracking-wider">Key Files ({keyFiles.length})</p>
                </div>
                <div className="divide-y divide-surface-700 max-h-48 overflow-y-auto">
                  {keyFiles.map(f => (
                    <div key={f} className="flex items-center gap-2 px-3 py-2 text-xs text-slate-300 font-mono">
                      <FileText size={11} className="text-muted flex-shrink-0" />
                      {f}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Ignored folders */}
            {(scanResult?.ignored_folders ?? []).length > 0 && (
              <div className="bg-surface-800 border border-surface-600 rounded-lg p-3">
                <p className="text-xs font-mono text-muted uppercase tracking-wider mb-2">Ignored Folders</p>
                <div className="flex flex-wrap gap-1.5">
                  {(scanResult?.ignored_folders ?? []).map(f => (
                    <span key={f} className="text-xs font-mono px-2 py-0.5 bg-surface-700 text-slate-400 rounded">{f}</span>
                  ))}
                </div>
              </div>
            )}

            {/* File manifest */}
            {manifest.length > 0 && (
              <div className="bg-surface-800 border border-surface-600 rounded-lg overflow-hidden">
                <div className="px-3 py-2 border-b border-surface-600 flex items-center justify-between">
                  <p className="text-xs font-mono text-muted uppercase tracking-wider">File Manifest</p>
                  <span className="text-xs text-muted">{manifest.length} entries</span>
                </div>
                <div className="max-h-64 overflow-y-auto divide-y divide-surface-700">
                  {manifest.slice(0, 200).map(f => (
                    <div key={f.id} className="flex items-center gap-2 px-3 py-1.5 text-xs">
                      <FileText size={10} className={f.is_key_file ? 'text-accent-400' : 'text-muted'} />
                      <span className="flex-1 font-mono text-slate-300 truncate">{f.relative_path}</span>
                      {f.detected_language && (
                        <span className="text-muted flex-shrink-0">{f.detected_language}</span>
                      )}
                    </div>
                  ))}
                  {manifest.length > 200 && (
                    <p className="px-3 py-2 text-xs text-muted italic">…and {manifest.length - 200} more</p>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
