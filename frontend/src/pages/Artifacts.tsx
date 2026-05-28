import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Archive, FileText, ExternalLink, Monitor, Eye, EyeOff, Maximize2, Trash2, FolderSearch, RefreshCw } from 'lucide-react'
import { buildsApi } from '../api/builds'
import { contextApi } from '../api/context'
import StatusBadge from '../components/StatusBadge'
import type { Build, BuildDirectoryConfig } from '../types'
import { formatDistanceToNow } from 'date-fns'

interface BuildWithDirs extends Build {
  dirConfig?: BuildDirectoryConfig | null
  hasHtml?: boolean
}

function PreviewPanel({ build }: { build: BuildWithDirs }) {
  const [visible, setVisible] = useState(false)
  if (!build.hasHtml) return null
  const src = `/api/builds/${build.id}/serve/`
  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg overflow-hidden">
      <button
        onClick={() => setVisible(v => !v)}
        className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-surface-700 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Monitor size={14} className="text-accent-400" />
          <span className="text-xs text-muted uppercase tracking-wider">Live Preview</span>
          <span className="text-xs text-slate-500">(sandboxed)</span>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={src}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            className="flex items-center gap-1 text-xs text-accent-400 hover:text-accent-300 px-2 py-0.5 rounded border border-accent-500/30 hover:border-accent-500/60 transition-colors"
          >
            <Maximize2 size={10} /> Popout
          </a>
          {visible ? <EyeOff size={14} className="text-muted" /> : <Eye size={14} className="text-muted" />}
        </div>
      </button>
      {visible && (
        <div className="border-t border-surface-600">
          <iframe
            src={src}
            className="w-full bg-white"
            style={{ height: '480px' }}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            title="Build preview"
          />
        </div>
      )}
    </div>
  )
}

export default function Artifacts() {
  const [builds, setBuilds] = useState<BuildWithDirs[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<BuildWithDirs | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [files, setFiles] = useState<any[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { builds: list } = await buildsApi.list(0, 200)
      const completed = list.filter(b => b.status === 'completed')
      const enriched = await Promise.all(
        completed.map(async b => {
          try {
            const [dirConfig, fd] = await Promise.all([
              contextApi.getBuildDirectories(b.id),
              buildsApi.files(b.id),
            ])
            const hasHtml = fd.files.some((f: any) => f.file_name?.toLowerCase().endsWith('.html'))
            return { ...b, dirConfig, hasHtml }
          } catch {
            return { ...b, dirConfig: null, hasHtml: false }
          }
        })
      )
      setBuilds(enriched)
    } catch { }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const selectBuild = async (b: BuildWithDirs) => {
    setSelected(b)
    try {
      const fd = await buildsApi.files(b.id)
      setFiles(fd.files)
    } catch { setFiles([]) }
  }

  const handleDelete = async (b: BuildWithDirs, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm(`Delete "${b.project_name}"? This removes the build and all generated files.`)) return
    setDeleting(b.id)
    try {
      await buildsApi.deleteBuild(b.id)
      setBuilds(prev => prev.filter(x => x.id !== b.id))
      if (selected?.id === b.id) { setSelected(null); setFiles([]) }
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Delete failed')
    }
    setDeleting(null)
  }

  if (loading) {
    return <div className="flex-1 flex items-center justify-center text-muted font-mono text-sm">Loading artifacts…</div>
  }

  return (
    <div className="flex-1 overflow-hidden flex">
      {/* Build list */}
      <div className="w-72 flex-shrink-0 border-r border-surface-700 overflow-y-auto">
        <div className="px-3 py-3 border-b border-surface-700 flex items-center justify-between">
          <p className="text-xs font-mono font-semibold text-muted uppercase tracking-wider">
            Completed Builds ({builds.length})
          </p>
          <button onClick={load} className="text-muted hover:text-slate-200 transition-colors">
            <RefreshCw size={12} />
          </button>
        </div>
        {builds.length === 0 && (
          <p className="text-muted text-xs p-4 font-mono italic">No completed builds yet.</p>
        )}
        {builds.map(b => (
          <div
            key={b.id}
            onClick={() => selectBuild(b)}
            className={`px-3 py-3 cursor-pointer border-b border-surface-700 transition-colors group relative ${
              selected?.id === b.id ? 'bg-surface-700' : 'hover:bg-surface-700/50'
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-mono font-medium text-slate-200 truncate max-w-[150px]">
                {b.project_name}
              </span>
              <div className="flex items-center gap-1">
                <StatusBadge status={b.status} />
                <button
                  onClick={e => handleDelete(b, e)}
                  disabled={deleting === b.id}
                  className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-400 transition-all ml-1"
                  title="Delete build"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
            <p className="text-xs text-muted">
              {formatDistanceToNow(new Date(b.created_at + 'Z'), { addSuffix: true })}
            </p>
            {b.hasHtml && (
              <span className="text-xs text-accent-400 font-mono">● HTML preview available</span>
            )}
          </div>
        ))}
      </div>

      {/* Detail pane */}
      <div className="flex-1 overflow-y-auto p-5">
        {!selected ? (
          <div className="flex flex-col items-center justify-center h-64 text-muted text-sm font-mono">
            <Archive size={32} className="mb-3 opacity-40" />
            Select a completed build to view its artifacts.
          </div>
        ) : (
          <div className="space-y-5 max-w-3xl">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-lg font-semibold font-mono text-slate-200">{selected.project_name}</h1>
                <p className="text-xs text-muted mt-0.5 font-mono">{selected.id}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={async () => {
                    try { await buildsApi.openFolder(selected.id) }
                    catch { alert('Could not open folder') }
                  }}
                  className="flex items-center gap-1.5 text-xs text-muted hover:text-slate-200 border border-surface-600 px-2 py-1.5 rounded transition-colors"
                >
                  <FolderSearch size={12} /> Open Folder
                </button>
                <Link
                  to={`/builds/${selected.id}`}
                  className="flex items-center gap-1.5 text-xs text-accent-400 hover:text-accent-300 border border-accent-500/30 px-2 py-1.5 rounded transition-colors"
                >
                  <ExternalLink size={12} /> Build Detail
                </Link>
                <button
                  onClick={e => handleDelete(selected, e)}
                  disabled={deleting === selected.id}
                  className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 border border-red-800 px-2 py-1.5 rounded transition-colors"
                >
                  <Trash2 size={12} /> Delete
                </button>
              </div>
            </div>

            {/* Live Preview */}
            <PreviewPanel build={selected} />

            {/* Meta */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: 'Status', value: selected.status },
                { label: 'Mode', value: selected.mode },
                { label: 'Stack', value: selected.stack_target },
                { label: 'Retries', value: String(selected.retry_count) },
              ].map(({ label, value }) => (
                <div key={label} className="bg-surface-800 border border-surface-600 rounded p-3">
                  <p className="text-xs text-muted mb-1">{label}</p>
                  <p className="text-sm font-mono text-slate-200">{value}</p>
                </div>
              ))}
            </div>

            {/* Generated files */}
            {files.length > 0 && (
              <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
                <p className="text-xs text-muted uppercase tracking-wider mb-3">Generated Files ({files.length})</p>
                <div className="space-y-1">
                  {files.map((f: any) => (
                    <div key={f.id || f.file_name} className="flex items-center justify-between text-xs font-mono">
                      <span className="text-slate-300">{f.file_name || f.relative_path}</span>
                      <span className="text-muted">{f.size_bytes ? `${(f.size_bytes / 1024).toFixed(1)}KB` : ''}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Directory info */}
            <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-2">
              <p className="text-xs font-mono font-semibold text-muted uppercase tracking-wider mb-2">Build Directories</p>
              {[
                { label: 'Source Dir', value: selected.dirConfig?.source_dir },
                { label: 'Workspace Dir', value: selected.dirConfig?.workspace_dir },
                { label: 'Output Dir', value: selected.dirConfig?.output_dir },
                { label: 'Final Output Path', value: selected.dirConfig?.final_output_path },
              ].map(({ label, value }) => (
                <div key={label}>
                  <p className="text-xs text-muted mb-0.5">{label}</p>
                  <p className={`text-xs font-mono truncate ${value ? 'text-slate-300' : 'text-surface-500 italic'}`}>
                    {value || '—'}
                  </p>
                </div>
              ))}
              {selected.dirConfig?.files_written != null && selected.dirConfig.files_written > 0 && (
                <div className="flex items-center gap-2 pt-1">
                  <FileText size={12} className="text-teal-400" />
                  <span className="text-xs text-teal-400 font-mono">
                    {selected.dirConfig.files_written} file{selected.dirConfig.files_written !== 1 ? 's' : ''} written
                  </span>
                </div>
              )}
            </div>

            {/* Requirement */}
            <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
              <p className="text-xs text-muted uppercase tracking-wider mb-2">Requirement</p>
              <p className="text-sm text-slate-300 font-mono whitespace-pre-wrap">{selected.requirement}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
