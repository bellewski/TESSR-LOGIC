import { useEffect, useState, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, FolderOpen, FileText, Play, Loader2, Terminal, ExternalLink, Activity, XCircle } from 'lucide-react'
import { buildsApi } from '../api/builds'
import { contextApi } from '../api/context'
import { useBuild } from '../hooks/useBuilds'
import { useBuildEvents } from '../hooks/useBuildEvents'
import StatusBadge from '../components/StatusBadge'
import PhasePill from '../components/PhasePill'
import EventLog from '../components/EventLog'
import FilesViewer from '../components/FilesViewer'
import FindingsPanel from '../components/FindingsPanel'
import type { Build, GeneratedFile, Finding, WsEvent, BuildDirectoryConfig } from '../types'
import { formatDistanceToNow } from 'date-fns'

function SmokeTestPanel({ events }: { events: WsEvent[] }) {
  const [open, setOpen] = useState(false)
  const smokeEvent = [...events].reverse().find(
    e => e.phase === 'testing' && (e.event_type === 'phase_complete' || e.event_type === 'phase_error')
  )
  useEffect(() => { if (smokeEvent) setOpen(true) }, [smokeEvent?.timestamp])
  if (!smokeEvent) return null

  let payload: any = null
  try { payload = JSON.parse(smokeEvent.payload || '{}') } catch { /* ignore */ }
  const results = payload?.results || []
  const passed = payload?.passed || 0
  const failed = payload?.failed || 0

  return (
    <div className="bg-surface-800 border border-pink-500/30 rounded-lg p-4">
      <button onClick={() => setOpen(o => !o)} className="flex items-center justify-between w-full text-left">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-pink-400" />
          <p className="text-xs text-muted uppercase tracking-wider">QA / Smoke Tests</p>
          <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${failed > 0 ? 'bg-red-900/40 text-red-400' : 'bg-green-900/40 text-green-400'}`}>
            {passed} passed / {failed} failed
          </span>
        </div>
        <span className="text-xs text-muted">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="mt-3 space-y-1 max-h-80 overflow-y-auto">
          {results.length === 0 && <p className="text-xs text-muted font-mono">No detailed results.</p>}
          {results.map((r: any, i: number) => (
            <div key={i} className={`flex items-center gap-2 text-xs font-mono px-2 py-1 rounded ${
              r.s === 'pass' ? 'text-green-400' : r.s === 'warn' ? 'text-yellow-400' : 'text-red-400'
            }`}>
              <span>{r.s === 'pass' ? '✓' : r.s === 'warn' ? '⚠' : '✗'}</span>
              <span className="flex-1">{r.t}: {r.d}</span>
            </div>
          ))}
          {payload?.fix_feedback && (
            <pre className="mt-2 text-xs font-mono text-yellow-300 whitespace-pre-wrap bg-surface-900 rounded p-2">
              {payload.fix_feedback}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

function BuildLogPanel({ events }: { events: WsEvent[] }) {
  const [open, setOpen] = useState(false)

  // Find the latest builder completion/error event
  const builderEvent = [...events].reverse().find(
    e => e.phase === 'building' && (e.event_type === 'phase_complete' || e.event_type === 'phase_error')
  )

  // Auto-open once builder event arrives
  useEffect(() => {
    if (builderEvent) setOpen(true)
  }, [builderEvent?.timestamp])

  if (!builderEvent) return null

  let payload: any = null
  try { payload = JSON.parse(builderEvent.payload || '{}') } catch { /* ignore */ }

  const lines = [
    `Type: ${payload?.project_type || 'unknown'}`,
    `Commands: ${(payload?.commands_run || []).join(', ') || 'none'}`,
    `Artifacts: ${(payload?.artifacts || []).length}`,
    `---`,
    payload?.log_preview || builderEvent.message || 'No log output.',
  ]
  if (builderEvent.event_type === 'phase_error') {
    lines.unshift(`ERROR: ${builderEvent.message}`)
  }
  const log = lines.join('\n')

  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center justify-between w-full text-left"
      >
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-lime-400" />
          <p className="text-xs text-muted uppercase tracking-wider">Build & Run Log</p>
        </div>
        <span className="text-xs text-muted">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <pre className="mt-3 text-xs font-mono text-slate-300 whitespace-pre-wrap bg-surface-900 rounded p-3 max-h-80 overflow-y-auto">
          {log}
        </pre>
      )}
    </div>
  )
}

function BuildProgress({ phase, status }: { phase: string | null; status: string }) {
  if (!phase || status === 'completed') return null
  const steps = ['architecting', 'coding', 'designing', 'hardening', 'validating', 'building', 'testing']
  const currentIdx = steps.indexOf(phase ?? '')
  const pct = Math.round(((currentIdx + 0.5) / steps.length) * 100)

  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted font-mono uppercase tracking-wider">Build Progress</span>
        <span className="text-xs text-lime-400 font-mono animate-pulse">{pct}%</span>
      </div>
      <div className="h-2 bg-surface-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-lime-500 to-emerald-400 transition-all duration-700 ease-out animate-pulse"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex gap-1.5">
        {steps.map((s, i) => (
          <span
            key={s}
            className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
              i < currentIdx ? 'bg-green-900/40 text-green-400'
              : i === currentIdx ? 'bg-lime-900/40 text-lime-400 animate-pulse'
              : 'bg-surface-700 text-muted'
            }`}
          >
            {s}
          </span>
        ))}
      </div>
    </div>
  )
}

function LaunchPanel({ build, files }: { build: Build; files: GeneratedFile[] }) {
  if (build.status !== 'completed') return null

  const hasHtml = files.some((f) => f.file_name.toLowerCase().endsWith('.html'))
  const hasPackageJson = files.some((f) => f.file_name.toLowerCase().endsWith('package.json'))
  const hasPy = files.some((f) => f.file_name.toLowerCase().endsWith('.py'))
  const runnable = hasHtml || hasPackageJson || hasPy

  const handleLaunch = () => {
    if (!runnable || files.length === 0) return
    if (hasHtml) {
      window.open(`/api/builds/${build.id}/serve/`, '_blank')
    } else if (hasPackageJson) {
      alert('Run: cd build/src && npm install && npm start')
    } else if (hasPy) {
      alert('Run: cd build/src && python app.py')
    }
  }

  return (
    <div className="bg-surface-800 border border-accent-500/30 rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Play size={14} className="text-accent-400" />
        <span className="text-xs text-muted font-mono uppercase tracking-wider">Launch Application</span>
      </div>
      <p className="text-xs text-slate-300">
        {hasHtml
          ? 'Open the generated HTML application in your browser.'
          : hasPackageJson
          ? 'Start the Node.js server. The command has been copied to your clipboard.'
          : hasPy
          ? 'Start the Python application. The command has been copied to your clipboard.'
          : 'No runnable application found in this build.'}
      </p>
      <button
        onClick={handleLaunch}
        disabled={!runnable}
        className="flex items-center gap-2 px-4 py-2 text-xs bg-accent-500 hover:bg-accent-400 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded transition-colors font-medium"
      >
        <ExternalLink size={12} />
        {hasHtml ? 'Open in Browser' : hasPackageJson || hasPy ? 'Copy Run Command' : 'Not Runnable'}
      </button>
    </div>
  )
}

function RerunButton({ buildId, onRerun }: { buildId: string; onRerun: () => void }) {
  const [rerunning, setRerunning] = useState(false)
  const navigate = useNavigate()

  const handleRerun = async () => {
    setRerunning(true)
    try {
      const newBuild = await buildsApi.rerun(buildId)
      navigate(`/builds/${newBuild.id}`)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Rerun failed')
    } finally {
      setRerunning(false)
    }
  }

  return (
    <button
      onClick={handleRerun}
      disabled={rerunning}
      className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-accent-500 hover:bg-accent-400 disabled:opacity-50 text-white rounded transition-colors"
    >
      {rerunning ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
      {rerunning ? 'Queuing...' : 'Rerun'}
    </button>
  )
}

export default function BuildDetail() {
  const { id } = useParams<{ id: string }>()
  const { build, setBuild, loading, refetch } = useBuild(id ?? null)
  const { events: wsEvents, connected } = useBuildEvents(id ?? null)
  const [files, setFiles] = useState<GeneratedFile[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [dirConfig, setDirConfig] = useState<BuildDirectoryConfig | null>(null)

  const loadSideData = useCallback(async () => {
    if (!id) return
    try {
      const [fd, fn] = await Promise.all([buildsApi.files(id), buildsApi.findings(id)])
      setFiles(fd.files)
      setFindings(fn.findings)
    } catch { /* silent */ }
    try {
      const dc = await contextApi.getBuildDirectories(id)
      setDirConfig(dc)
    } catch { /* no dir config */ }
  }, [id])

  useEffect(() => { loadSideData() }, [loadSideData])

  // Auto-refresh build status while running
  useEffect(() => {
    if (!build || !['running', 'queued'].includes(build.status)) return
    const timer = setInterval(() => {
      refetch()
      loadSideData()
    }, 3000)
    return () => clearInterval(timer)
  }, [build?.status, refetch, loadSideData])

  // Refresh when a pipeline_complete or pipeline_error event arrives
  useEffect(() => {
    const last = wsEvents[wsEvents.length - 1] as WsEvent | undefined
    if (last && ['pipeline_complete', 'pipeline_error'].includes(last.event_type)) {
      refetch()
      loadSideData()
    }
  }, [wsEvents.length])

  if (loading && !build) {
    return <div className="flex-1 flex items-center justify-center text-muted font-mono text-sm">Loading...</div>
  }

  if (!build) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3">
        <p className="text-muted">Build not found.</p>
        <Link to="/" className="text-accent-400 text-sm hover:underline">← Back to Dashboard</Link>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-muted hover:text-slate-200 transition-colors">
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-semibold text-slate-200 font-mono">{build.project_name}</h1>
              <StatusBadge status={build.status} />
              {build.current_phase && <PhasePill phase={build.current_phase} />}
            </div>
            <p className="text-xs text-muted mt-0.5 font-mono">{build.id}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(build.status === 'failed' || build.status === 'completed') && (
            <RerunButton buildId={build.id} onRerun={refetch} />
          )}
          {(build.status === 'running' || build.status === 'queued') && (
            <button
              onClick={async () => {
                await buildsApi.cancel(build.id)
                refetch()
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 border border-red-700 rounded transition-colors"
            >
              <XCircle size={12} />
              Cancel
            </button>
          )}
          <button
            onClick={() => { refetch(); loadSideData() }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted hover:text-slate-200 border border-surface-600 rounded transition-colors"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
        </div>
      </div>

      {/* Meta */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Stack', value: build.stack_target },
          { label: 'Mode',  value: build.mode },
          { label: 'Retries', value: String(build.retry_count) },
          { label: 'Created', value: formatDistanceToNow(new Date(build.created_at + 'Z'), { addSuffix: true }) },
        ].map(({ label, value }) => (
          <div key={label} className="bg-surface-800 border border-surface-600 rounded p-3">
            <p className="text-xs text-muted mb-1">{label}</p>
            <p className="text-sm font-mono text-slate-200 truncate">{value}</p>
          </div>
        ))}
      </div>

      {/* Progress bar while building */}
      <BuildProgress phase={build.current_phase} status={build.status} />

      {/* Requirement */}
      <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
        <p className="text-xs text-muted mb-2 uppercase tracking-wider">Requirement</p>
        <p className="text-sm text-slate-300 whitespace-pre-wrap font-mono">{build.requirement}</p>
      </div>

      {build.error_message && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-3 text-sm text-red-300 font-mono">
          {build.error_message}
        </div>
      )}

      {/* Directory config */}
      {dirConfig && (
        <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <FolderOpen size={14} className="text-muted" />
            <p className="text-xs text-muted uppercase tracking-wider">Build Directories</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              { label: 'Source Dir',      value: dirConfig.source_dir },
              { label: 'Workspace Dir',   value: dirConfig.workspace_dir },
              { label: 'Output Dir',      value: dirConfig.output_dir },
              { label: 'Final Output',    value: dirConfig.final_output_path },
            ].map(({ label, value }) => value ? (
              <div key={label}>
                <p className="text-xs text-muted mb-0.5">{label}</p>
                <p className="text-xs font-mono text-slate-300 truncate">{value}</p>
              </div>
            ) : null)}
            {dirConfig.files_written > 0 && (
              <div className="flex items-center gap-1.5 col-span-full">
                <FileText size={12} className="text-teal-400" />
                <span className="text-xs text-teal-400 font-mono">{dirConfig.files_written} files written to output</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Event log */}
      <EventLog events={wsEvents} connected={connected} />

      {/* Build log */}
      <BuildLogPanel events={wsEvents} />

      {/* QA / Smoke tests */}
      <SmokeTestPanel events={wsEvents} />

      {/* Launch application after completion */}
      <LaunchPanel build={build} files={files} />

      {/* Files */}
      <FilesViewer files={files} />

      {/* Findings */}
      <FindingsPanel findings={findings} />
    </div>
  )
}
