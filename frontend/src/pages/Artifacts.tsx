import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Archive, FolderOpen, FileText, ExternalLink } from 'lucide-react'
import { buildsApi } from '../api/builds'
import { contextApi } from '../api/context'
import StatusBadge from '../components/StatusBadge'
import type { Build, BuildDirectoryConfig } from '../types'
import { formatDistanceToNow } from 'date-fns'

interface BuildWithDirs extends Build {
  dirConfig?: BuildDirectoryConfig | null
}

export default function Artifacts() {
  const [builds, setBuilds] = useState<BuildWithDirs[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<BuildWithDirs | null>(null)

  useEffect(() => {
    buildsApi.list(0, 100).then(async ({ builds: list }) => {
      const enriched = await Promise.all(
        list
          .filter(b => b.status === 'completed' || b.status === 'failed')
          .map(async b => {
            try {
              const dirConfig = await contextApi.getBuildDirectories(b.id)
              return { ...b, dirConfig }
            } catch {
              return { ...b, dirConfig: null }
            }
          })
      )
      setBuilds(enriched)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted font-mono text-sm">
        Loading artifacts…
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-hidden flex">
      {/* Build list */}
      <div className="w-72 flex-shrink-0 border-r border-surface-700 overflow-y-auto">
        <div className="px-3 py-3 border-b border-surface-700">
          <p className="text-xs font-mono font-semibold text-muted uppercase tracking-wider">
            Completed Builds ({builds.length})
          </p>
        </div>
        {builds.length === 0 && (
          <p className="text-muted text-xs p-4 font-mono italic">No completed builds yet.</p>
        )}
        {builds.map(b => (
          <div
            key={b.id}
            onClick={() => setSelected(b)}
            className={`px-3 py-3 cursor-pointer border-b border-surface-700 transition-colors ${
              selected?.id === b.id ? 'bg-surface-700' : 'hover:bg-surface-700/50'
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-mono font-medium text-slate-200 truncate max-w-[160px]">
                {b.project_name}
              </span>
              <StatusBadge status={b.status} />
            </div>
            <p className="text-xs text-muted">
              {formatDistanceToNow(new Date(b.created_at + 'Z'), { addSuffix: true })}
            </p>
            {b.dirConfig?.final_output_path && (
              <p className="text-xs text-teal-400 font-mono truncate mt-0.5">
                {b.dirConfig.final_output_path}
              </p>
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
          <div className="space-y-5 max-w-2xl">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-lg font-semibold font-mono text-slate-200">{selected.project_name}</h1>
                <p className="text-xs text-muted mt-0.5 font-mono">{selected.id}</p>
              </div>
              <Link
                to={`/builds/${selected.id}`}
                className="flex items-center gap-1.5 text-xs text-accent-400 hover:underline"
              >
                <ExternalLink size={12} /> Open Build Detail
              </Link>
            </div>

            {/* Directory info */}
            <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-3">
              <p className="text-xs font-mono font-semibold text-muted uppercase tracking-wider">
                Build Directories
              </p>
              {[
                { label: 'Source Dir', value: selected.dirConfig?.source_dir },
                { label: 'Workspace Dir', value: selected.dirConfig?.workspace_dir },
                { label: 'Output Dir', value: selected.dirConfig?.output_dir },
                { label: 'Final Output Path', value: selected.dirConfig?.final_output_path },
              ].map(({ label, value }) => (
                <div key={label}>
                  <p className="text-xs text-muted mb-0.5">{label}</p>
                  <p className={`text-sm font-mono ${value ? 'text-slate-200' : 'text-surface-500 italic'}`}>
                    {value || '—'}
                  </p>
                </div>
              ))}
              {selected.dirConfig?.files_written != null && selected.dirConfig.files_written > 0 && (
                <div className="flex items-center gap-2 mt-1">
                  <FileText size={12} className="text-teal-400" />
                  <span className="text-xs text-teal-400 font-mono">
                    {selected.dirConfig.files_written} file{selected.dirConfig.files_written !== 1 ? 's' : ''} written
                  </span>
                </div>
              )}
            </div>

            {/* Build metadata */}
            <div className="grid grid-cols-2 gap-3">
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

            {/* Requirement */}
            <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
              <p className="text-xs text-muted uppercase tracking-wider mb-2">Requirement</p>
              <p className="text-sm text-slate-300 font-mono whitespace-pre-wrap">{selected.requirement}</p>
            </div>

            {selected.error_message && (
              <div className="bg-red-900/20 border border-red-800 rounded p-3 text-sm text-red-300 font-mono">
                {selected.error_message}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
