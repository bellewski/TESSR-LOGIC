import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Play, Clock, CheckCircle2, XCircle, Activity, Trash2 } from 'lucide-react'
import { buildsApi } from '../api/builds'
import StatusBadge from '../components/StatusBadge'
import PhasePill from '../components/PhasePill'
import type { Build } from '../types'

const PHASE_ORDER = ['architecting', 'coding', 'designing', 'hardening', 'validating', 'building', 'testing']

function PhaseTimeline({ build }: { build: Build }) {
  return (
    <div className="flex items-center gap-0">
      {PHASE_ORDER.map((phase, i) => {
        const isActive = build.current_phase === phase && build.status === 'running'
        const isDone =
          build.status === 'completed' ||
          (build.current_phase && PHASE_ORDER.indexOf(build.current_phase) > i)
        const isFailed = build.status === 'failed' && build.current_phase === phase

        return (
          <div key={phase} className="flex items-center">
            <div className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono border transition-all ${
              isActive
                ? 'bg-accent-500/20 border-accent-500 text-accent-300 animate-pulse'
                : isDone
                ? 'bg-green-900/20 border-green-700 text-green-400'
                : isFailed
                ? 'bg-red-900/20 border-red-700 text-red-400'
                : 'bg-surface-700 border-surface-600 text-muted'
            }`}>
              {isActive && <Loader2 size={10} className="animate-spin" />}
              {isDone && <CheckCircle2 size={10} />}
              {isFailed && <XCircle size={10} />}
              {phase}
            </div>
            {i < PHASE_ORDER.length - 1 && (
              <div className={`w-4 h-px mx-0.5 ${isDone ? 'bg-green-700' : 'bg-surface-600'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function BuildPipeline() {
  const [builds, setBuilds] = useState<Build[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [clearing, setClearing] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)

  const load = () =>
    buildsApi.list(0, 200).then(({ builds: list }) => {
      setBuilds(list)
      setLoading(false)
    }).catch(() => setLoading(false))

  useEffect(() => {
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [])

  const failedBuilds = builds.filter(b => b.status === 'failed')

  const clearAllFailed = async () => {
    if (failedBuilds.length === 0) return
    if (!confirm(`Delete all ${failedBuilds.length} failed build${failedBuilds.length !== 1 ? 's' : ''}? This cannot be undone.`)) return
    setClearing(true)
    await Promise.allSettled(failedBuilds.map(b => buildsApi.deleteBuild(b.id)))
    setClearing(false)
    load()
  }

  const deleteSingle = async (b: Build, e: React.MouseEvent) => {
    e.preventDefault()
    if (!confirm(`Delete "${b.project_name}"?`)) return
    setDeleting(b.id)
    try {
      await buildsApi.deleteBuild(b.id)
      setBuilds(prev => prev.filter(x => x.id !== b.id))
    } catch { }
    setDeleting(null)
  }

  const filtered = filter === 'all'
    ? builds
    : builds.filter(b => b.status === filter)

  const counts = builds.reduce((acc, b) => {
    acc[b.status] = (acc[b.status] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted font-mono text-sm">
        <Loader2 size={18} className="animate-spin mr-2" /> Loading pipeline…
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-surface-700 flex-shrink-0">
        <div>
          <h1 className="text-base font-semibold text-slate-200">Build Pipeline</h1>
          <p className="text-xs text-muted mt-0.5">All builds across all phases</p>
        </div>
        <div className="flex items-center gap-2">
          {builds.some(b => b.status === 'running' || b.status === 'queued') && (
            <span className="flex items-center gap-1.5 text-xs text-green-400 font-mono">
              <Activity size={12} className="animate-pulse" /> Live
            </span>
          )}
          {failedBuilds.length > 0 && (
            <button
              onClick={clearAllFailed}
              disabled={clearing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 border border-red-800 hover:border-red-700 rounded transition-colors disabled:opacity-50"
            >
              <Trash2 size={12} />
              {clearing ? 'Clearing...' : `Clear Failed (${failedBuilds.length})`}
            </button>
          )}
          <Link
            to="/"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-accent-500 hover:bg-accent-400 text-white rounded transition-colors"
          >
            <Play size={12} /> New Build
          </Link>
        </div>
      </div>

      {/* Status filter tabs */}
      <div className="flex items-center gap-1 px-5 py-2 border-b border-surface-700 flex-shrink-0">
        {[
          { key: 'all', label: `All (${builds.length})` },
          { key: 'running', label: `Running (${counts.running || 0})` },
          { key: 'queued', label: `Queued (${counts.queued || 0})` },
          { key: 'completed', label: `Done (${counts.completed || 0})` },
          { key: 'failed', label: `Failed (${counts.failed || 0})` },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`px-3 py-1 rounded text-xs font-mono transition-colors ${
              filter === key
                ? 'bg-accent-500 text-white'
                : 'text-muted hover:text-slate-200 hover:bg-surface-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Build rows */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center h-48 text-muted font-mono text-sm">
            <Clock size={28} className="mb-2 opacity-40" />
            No builds match this filter.
          </div>
        )}
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface-800 border-b border-surface-700">
            <tr className="text-left text-xs font-mono text-muted">
              <th className="px-5 py-2.5">Project</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5">Phase Timeline</th>
              <th className="px-3 py-2.5">Mode</th>
              <th className="px-3 py-2.5">Stack</th>
              <th className="px-3 py-2.5">Started</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-700">
            {filtered.map(b => (
              <tr key={b.id} className="hover:bg-surface-700/40 transition-colors group">
                <td className="px-5 py-3">
                  <p className="font-mono font-medium text-slate-200 truncate max-w-[180px]">{b.project_name}</p>
                  <p className="text-xs text-muted font-mono mt-0.5 truncate max-w-[180px]">{b.id.slice(0, 8)}…</p>
                </td>
                <td className="px-3 py-3">
                  <StatusBadge status={b.status} />
                </td>
                <td className="px-3 py-3">
                  <PhaseTimeline build={b} />
                </td>
                <td className="px-3 py-3">
                  <span className="text-xs font-mono text-slate-400">{b.mode}</span>
                </td>
                <td className="px-3 py-3">
                  <span className="text-xs font-mono text-slate-400 truncate max-w-[100px] block">{b.stack_target}</span>
                </td>
                <td className="px-3 py-3">
                  <span className="text-xs text-muted">
                    {new Date(b.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                  </span>
                </td>
                <td className="px-3 py-3">
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/builds/${b.id}`}
                      className="text-xs text-accent-400 hover:underline font-mono"
                    >
                      View →
                    </Link>
                    <button
                      onClick={e => deleteSingle(b, e)}
                      disabled={deleting === b.id}
                      className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-400 transition-all"
                      title="Delete build"
                    >
                      {deleting === b.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
import { buildsApi } from '../api/builds'
import StatusBadge from '../components/StatusBadge'
import PhasePill from '../components/PhasePill'
import type { Build } from '../types'

const PHASE_ORDER = ['architecting', 'coding', 'designing', 'hardening', 'validating', 'building', 'testing']

function PhaseTimeline({ build }: { build: Build }) {
  return (
    <div className="flex items-center gap-0">
      {PHASE_ORDER.map((phase, i) => {
        const isActive = build.current_phase === phase && build.status === 'running'
        const isDone =
          build.status === 'completed' ||
          (build.current_phase && PHASE_ORDER.indexOf(build.current_phase) > i)
        const isFailed = build.status === 'failed' && build.current_phase === phase

        return (
          <div key={phase} className="flex items-center">
            <div className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono border transition-all ${
              isActive
                ? 'bg-accent-500/20 border-accent-500 text-accent-300 animate-pulse'
                : isDone
                ? 'bg-green-900/20 border-green-700 text-green-400'
                : isFailed
                ? 'bg-red-900/20 border-red-700 text-red-400'
                : 'bg-surface-700 border-surface-600 text-muted'
            }`}>
              {isActive && <Loader2 size={10} className="animate-spin" />}
              {isDone && <CheckCircle2 size={10} />}
              {isFailed && <XCircle size={10} />}
              {phase}
            </div>
            {i < PHASE_ORDER.length - 1 && (
              <div className={`w-4 h-px mx-0.5 ${isDone ? 'bg-green-700' : 'bg-surface-600'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function BuildPipeline() {
  const [builds, setBuilds] = useState<Build[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  const load = () =>
    buildsApi.list(0, 100).then(({ builds: list }) => {
      setBuilds(list)
      setLoading(false)
    }).catch(() => setLoading(false))

  useEffect(() => {
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [])

  const filtered = filter === 'all'
    ? builds
    : builds.filter(b => b.status === filter)

  const counts = builds.reduce((acc, b) => {
    acc[b.status] = (acc[b.status] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted font-mono text-sm">
        <Loader2 size={18} className="animate-spin mr-2" /> Loading pipeline…
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-surface-700 flex-shrink-0">
        <div>
          <h1 className="text-base font-semibold text-slate-200">Build Pipeline</h1>
          <p className="text-xs text-muted mt-0.5">All builds across all phases</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Live indicator */}
          {builds.some(b => b.status === 'running' || b.status === 'queued') && (
            <span className="flex items-center gap-1.5 text-xs text-green-400 font-mono">
              <Activity size={12} className="animate-pulse" /> Live
            </span>
          )}
          <Link
            to="/"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-accent-500 hover:bg-accent-400 text-white rounded transition-colors"
          >
            <Play size={12} /> New Build
          </Link>
        </div>
      </div>

      {/* Status filter tabs */}
      <div className="flex items-center gap-1 px-5 py-2 border-b border-surface-700 flex-shrink-0">
        {[
          { key: 'all', label: `All (${builds.length})` },
          { key: 'running', label: `Running (${counts.running || 0})` },
          { key: 'queued', label: `Queued (${counts.queued || 0})` },
          { key: 'completed', label: `Done (${counts.completed || 0})` },
          { key: 'failed', label: `Failed (${counts.failed || 0})` },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`px-3 py-1 rounded text-xs font-mono transition-colors ${
              filter === key
                ? 'bg-accent-500 text-white'
                : 'text-muted hover:text-slate-200 hover:bg-surface-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Build rows */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center h-48 text-muted font-mono text-sm">
            <Clock size={28} className="mb-2 opacity-40" />
            No builds match this filter.
          </div>
        )}
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface-800 border-b border-surface-700">
            <tr className="text-left text-xs font-mono text-muted">
              <th className="px-5 py-2.5">Project</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5">Phase Timeline</th>
              <th className="px-3 py-2.5">Mode</th>
              <th className="px-3 py-2.5">Stack</th>
              <th className="px-3 py-2.5">Started</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-700">
            {filtered.map(b => (
              <tr key={b.id} className="hover:bg-surface-700/40 transition-colors">
                <td className="px-5 py-3">
                  <p className="font-mono font-medium text-slate-200 truncate max-w-[180px]">{b.project_name}</p>
                  <p className="text-xs text-muted font-mono mt-0.5 truncate max-w-[180px]">{b.id.slice(0, 8)}…</p>
                </td>
                <td className="px-3 py-3">
                  <StatusBadge status={b.status} />
                </td>
                <td className="px-3 py-3">
                  <PhaseTimeline build={b} />
                </td>
                <td className="px-3 py-3">
                  <span className="text-xs font-mono text-slate-400">{b.mode}</span>
                </td>
                <td className="px-3 py-3">
                  <span className="text-xs font-mono text-slate-400 truncate max-w-[100px] block">{b.stack_target}</span>
                </td>
                <td className="px-3 py-3">
                  <span className="text-xs text-muted">
                    {new Date(b.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                  </span>
                </td>
                <td className="px-3 py-3">
                  <Link
                    to={`/builds/${b.id}`}
                    className="text-xs text-accent-400 hover:underline font-mono"
                  >
                    View →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
