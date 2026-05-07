import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Play, Loader2, XCircle } from 'lucide-react'
import StatusBadge from './StatusBadge'
import PhasePill from './PhasePill'
import { buildsApi } from '../api/builds'
import type { Build } from '../types'

interface Props {
  builds: Build[]
  selectedId?: string | null
}

function RerunCell({ build }: { build: Build }) {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const rerun = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setLoading(true)
    try {
      const nb = await buildsApi.rerun(build.id)
      navigate(`/builds/${nb.id}`)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Rerun failed')
    } finally {
      setLoading(false)
    }
  }

  if (build.status !== 'failed' && build.status !== 'completed') return <span className="text-muted text-xs">—</span>

  return (
    <button
      onClick={rerun}
      disabled={loading}
      className="flex items-center gap-1 text-xs text-accent-400 hover:text-accent-300 transition-colors"
    >
      {loading ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
      {loading ? '…' : 'Rerun'}
    </button>
  )
}

function CancelCell({ build, onCancel }: { build: Build; onCancel?: () => void }) {
  const [loading, setLoading] = useState(false)

  const cancel = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setLoading(true)
    try {
      await buildsApi.cancel(build.id)
      onCancel?.()
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Cancel failed')
    } finally {
      setLoading(false)
    }
  }

  if (build.status !== 'running' && build.status !== 'queued') return <span className="text-muted text-xs">—</span>

  return (
    <button
      onClick={cancel}
      disabled={loading}
      className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors"
    >
      {loading ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />}
      {loading ? '…' : 'Cancel'}
    </button>
  )
}

export default function BuildTable({ builds, selectedId }: Props) {
  const navigate = useNavigate()

  if (builds.length === 0) {
    return (
      <div className="text-center py-16 text-muted text-sm font-mono">
        No builds yet — submit one above.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-600 text-left">
            <th className="pb-2 pr-4 text-xs font-semibold text-muted uppercase tracking-wider">Project</th>
            <th className="pb-2 pr-4 text-xs font-semibold text-muted uppercase tracking-wider">Stack</th>
            <th className="pb-2 pr-4 text-xs font-semibold text-muted uppercase tracking-wider">Status</th>
            <th className="pb-2 pr-4 text-xs font-semibold text-muted uppercase tracking-wider">Phase</th>
            <th className="pb-2 pr-4 text-xs font-semibold text-muted uppercase tracking-wider">Mode</th>
            <th className="pb-2 pr-4 text-xs font-semibold text-muted uppercase tracking-wider">Age</th>
            <th className="pb-2 text-xs font-semibold text-muted uppercase tracking-wider">Actions</th>
          </tr>
        </thead>
        <tbody>
          {builds.map(build => (
            <tr
              key={build.id}
              onClick={() => navigate(`/builds/${build.id}`)}
              className={`border-b border-surface-700 cursor-pointer transition-colors hover:bg-surface-700 ${
                selectedId === build.id ? 'bg-surface-700' : ''
              }`}
            >
              <td className="py-2.5 pr-4 font-medium text-slate-200 font-mono">{build.project_name}</td>
              <td className="py-2.5 pr-4 text-muted text-xs">{build.stack_target}</td>
              <td className="py-2.5 pr-4"><StatusBadge status={build.status} /></td>
              <td className="py-2.5 pr-4">
                {build.current_phase ? <PhasePill phase={build.current_phase} /> : <span className="text-muted text-xs">—</span>}
              </td>
              <td className="py-2.5 pr-4">
                <span className="text-xs font-mono text-muted">{build.mode}</span>
              </td>
              <td className="py-2.5 pr-4 text-xs text-muted">
                {formatDistanceToNow(new Date(build.created_at + 'Z'), { addSuffix: true })}
              </td>
              <td className="py-2.5">
                <div className="flex items-center gap-2">
                  <RerunCell build={build} />
                  <CancelCell build={build} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
