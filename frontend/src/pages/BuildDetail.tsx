import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, FolderOpen, FileText, Play, Loader2, Terminal,
  ExternalLink, Activity, XCircle, Monitor, GitBranch, Eye, EyeOff, Maximize2, FolderSearch } from 'lucide-react'
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

// ─── Phase timeline ──────────────────────────────────────────────────────────

const PHASE_ORDER = ['architecting','coding','designing','hardening','fixing','validating','building','testing'] as const
const PHASE_COLORS: Record<string, string> = {
  architecting: 'bg-purple-500',
  coding:       'bg-blue-500',
  designing:    'bg-pink-500',
  hardening:    'bg-orange-500',
  fixing:       'bg-yellow-500',
  validating:   'bg-cyan-500',
  building:     'bg-lime-500',
  testing:      'bg-emerald-500',
}

function PhaseTimeline({ events, status }: { events: WsEvent[]; status: string }) {
  // Calculate phase durations from events
  const phases: { phase: string; startMs: number; endMs: number }[] = []
  const starts: Record<string, number> = {}

  for (const e of events) {
    const phase = e.phase
    if (!phase) continue
    const ms = new Date(e.timestamp || e.created_at || '').getTime()
    if (isNaN(ms)) continue
    if (e.event_type === 'phase_start') {
      starts[phase] = ms
    } else if ((e.event_type === 'phase_complete' || e.event_type === 'phase_error') && starts[phase]) {
      phases.push({ phase, startMs: starts[phase], endMs: ms })
      delete starts[phase]
    }
  }

  if (phases.length === 0) return null

  const totalMs = phases.reduce((sum, p) => sum + (p.endMs - p.startMs), 0)
  const formatMs = (ms: number) => ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`

  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-2">
      <p className="text-xs text-muted uppercase tracking-wider mb-3">Phase Timeline</p>
      <div className="flex h-5 rounded overflow-hidden gap-px">
        {phases.map(({ phase, startMs, endMs }) => {
          const pct = Math.max(2, ((endMs - startMs) / totalMs) * 100)
          const color = PHASE_COLORS[phase] || 'bg-slate-500'
          return (
            <div
              key={phase}
              className={`${color} opacity-80 hover:opacity-100 transition-opacity`}
              style={{ width: `${pct}%` }}
              title={`${phase}: ${formatMs(endMs - startMs)}`}
            />
          )
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {phases.map(({ phase, startMs, endMs }) => (
          <div key={phase} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${PHASE_COLORS[phase] || 'bg-slate-500'}`} />
            <span className="text-xs font-mono text-muted">{phase}</span>
            <span className="text-xs font-mono text-slate-400">{formatMs(endMs - startMs)}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5 ml-auto">
          <span className="text-xs font-mono text-muted">total</span>
          <span className="text-xs font-mono text-slate-300">{formatMs(totalMs)}</span>
        </div>
      </div>
    </div>
  )
}

// ─── Refine with AI panel ─────────────────────────────────────────────────────

function RefinePanel({ build, files }: { build: Build; files: GeneratedFile[] }) {
  const editable = files.filter(f => /\.(html|css|js)$/i.test(f.file_name))
  const [file, setFile] = useState<string>('')
  const [instruction, setInstruction] = useState('')
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState<{ who: 'you' | 'ai'; text: string; err?: boolean }[]>([])

  if (build.status !== 'completed' || editable.length === 0) return null
  const selected = file || editable[0].file_name

  const submit = async () => {
    const text = instruction.trim()
    if (!text || busy) return
    setBusy(true)
    setLog(l => [...l, { who: 'you', text: `${selected}: ${text}` }])
    setInstruction('')
    try {
      const res = await buildsApi.refine(build.id, selected, text)
      setLog(l => [...l, { who: 'ai', text: res.message }])
      // reload any preview iframes so the change is visible immediately
      document.querySelectorAll<HTMLIFrameElement>('iframe[title="Build preview"]').forEach(f => { f.src = f.src })
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Refinement failed'
      setLog(l => [...l, { who: 'ai', text: msg, err: true }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <FileText size={14} className="text-accent-400" />
        <p className="text-xs text-muted uppercase tracking-wider">Refine with AI</p>
        <span className="text-xs text-slate-500">describe a change — the model edits the file in place</span>
      </div>
      {log.length > 0 && (
        <div className="mb-3 space-y-1.5 max-h-48 overflow-y-auto">
          {log.map((m, i) => (
            <p key={i} className={`text-xs font-mono ${m.who === 'you' ? 'text-slate-400' : m.err ? 'text-red-300' : 'text-teal-300'}`}>
              {m.who === 'you' ? '> ' : ''}{m.text}
            </p>
          ))}
          {busy && <p className="text-xs font-mono text-slate-500 animate-pulse">refining…</p>}
        </div>
      )}
      <div className="flex gap-2">
        <select
          value={selected}
          onChange={e => setFile(e.target.value)}
          className="bg-surface-900 border border-surface-600 rounded px-2 py-1.5 text-xs text-slate-300 font-mono"
        >
          {editable.map(f => (
            <option key={f.file_name} value={f.file_name}>{f.file_name}</option>
          ))}
        </select>
        <input
          value={instruction}
          onChange={e => setInstruction(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') submit() }}
          placeholder='e.g. "remove the Tasks link from the nav"'
          className="flex-1 bg-surface-900 border border-surface-600 rounded px-3 py-1.5 text-xs text-slate-200"
          disabled={busy}
        />
        <button
          onClick={submit}
          disabled={busy || !instruction.trim()}
          className="text-xs px-3 py-1.5 rounded border border-accent-500/40 text-accent-400 hover:text-accent-300 hover:border-accent-500/70 disabled:opacity-40 transition-colors"
        >
          {busy ? 'Working…' : 'Refine'}
        </button>
      </div>
    </div>
  )
}

// ─── Preview panel ────────────────────────────────────────────────────────────

function PreviewPanel({ build, files }: { build: Build; files: GeneratedFile[] }) {
  const [visible, setVisible] = useState(false)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  const hasHtml = files.some(f => f.file_name.toLowerCase().endsWith('.html'))
  if (build.status !== 'completed' || !hasHtml) return null

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
            ref={iframeRef}
            src={src}
            className="w-full bg-white"
            style={{ height: '520px' }}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            title="Build preview"
          />
        </div>
      )}
    </div>
  )
}

// ─── Diff view ────────────────────────────────────────────────────────────────

function DiffLine({ line }: { line: string }) {
  if (line.startsWith('+')) return <div className="text-green-400 bg-green-900/20 px-1">{line}</div>
  if (line.startsWith('-')) return <div className="text-red-400 bg-red-900/20 px-1">{line}</div>
  if (line.startsWith('@@')) return <div className="text-blue-400 opacity-60 px-1">{line}</div>
  return <div className="text-slate-400 px-1">{line}</div>
}

function simpleDiff(a: string, b: string, ctx = 3): string[] {
  const aLines = a.split('\n')
  const bLines = b.split('\n')
  const result: string[] = []
  let i = 0, j = 0
  while (i < aLines.length || j < bLines.length) {
    if (aLines[i] === bLines[j]) {
      result.push(` ${aLines[i]}`)
      i++; j++
    } else if (j < bLines.length && (i >= aLines.length || aLines[i] !== bLines[j])) {
      if (i < aLines.length && aLines[i] !== bLines[j]) {
        result.push(`-${aLines[i]}`); i++
      }
      result.push(`+${bLines[j]}`); j++
    } else {
      result.push(`-${aLines[i]}`); i++
    }
  }
  return result
}

function DiffPanel({ files }: { files: GeneratedFile[] }) {
  const [open, setOpen] = useState(false)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)

  // Group files by name across phases — only show files that appear in multiple phases
  const byName: Record<string, GeneratedFile[]> = {}
  for (const f of files) {
    const key = f.file_name
    if (!byName[key]) byName[key] = []
    byName[key].push(f)
  }
  const diffable = Object.entries(byName).filter(([, versions]) => versions.length > 1)
  if (diffable.length === 0) return null

  const selected = selectedFile ?? diffable[0]?.[0]
  const versions = selected ? (byName[selected] ?? []) : []
  const v1 = versions[0]?.content_preview ?? ''
  const v2 = versions[versions.length - 1]?.content_preview ?? ''
  const diffLines = simpleDiff(v1, v2)

  const adds = diffLines.filter(l => l.startsWith('+')).length
  const dels = diffLines.filter(l => l.startsWith('-')).length

  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-surface-700 transition-colors"
      >
        <div className="flex items-center gap-2">
          <GitBranch size={14} className="text-blue-400" />
          <span className="text-xs text-muted uppercase tracking-wider">Retry Diff</span>
          <span className="text-xs font-mono text-slate-500">{diffable.length} file{diffable.length !== 1 ? 's' : ''} changed across attempts</span>
        </div>
        <span className="text-xs text-muted">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="border-t border-surface-600">
          <div className="flex gap-1 px-3 py-2 border-b border-surface-600 overflow-x-auto">
            {diffable.map(([name]) => (
              <button
                key={name}
                onClick={() => setSelectedFile(name)}
                className={`text-xs font-mono px-2 py-1 rounded whitespace-nowrap transition-colors ${
                  selected === name
                    ? 'bg-blue-900/40 text-blue-400 border border-blue-700'
                    : 'text-muted hover:text-slate-200 border border-surface-600'
                }`}
              >
                {name}
              </button>
            ))}
          </div>
          {selected && (
            <>
              <div className="flex items-center gap-3 px-3 py-2 border-b border-surface-600">
                <span className="text-xs text-muted font-mono">{versions.length} versions ({versions.map(v => v.phase).join(' → ')})</span>
                <span className="text-xs font-mono text-green-400">+{adds}</span>
                <span className="text-xs font-mono text-red-400">-{dels}</span>
                <span className="text-xs text-slate-500">preview only (first 1KB)</span>
              </div>
              <pre className="text-xs font-mono text-slate-300 p-3 max-h-80 overflow-y-auto bg-surface-900 leading-5">
                {diffLines.map((line, i) => <DiffLine key={i} line={line} />)}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Existing panels (unchanged) ─────────────────────────────────────────────

function SmokeTestPanel({ events }: { events: WsEvent[] }) {
  const [open, setOpen] = useState(false)
  const smokeEvent = [...events].reverse().find(
    e => e.phase === 'testing' && (e.event_type === 'phase_complete' || e.event_type === 'phase_error')
  )
  useEffect(() => { if (smokeEvent) setOpen(true) }, [smokeEvent?.timestamp])
  if (!smokeEvent) return null

  let payload: any = null
  try { payload = JSON.parse(smokeEvent.payload || '{}') } catch { }
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
  const builderEvent = [...events].reverse().find(
    e => e.phase === 'building' && (e.event_type === 'phase_complete' || e.event_type === 'phase_error')
  )
  useEffect(() => { if (builderEvent) setOpen(true) }, [builderEvent?.timestamp])
  if (!builderEvent) return null

  let payload: any = null
  try { payload = JSON.parse(builderEvent.payload || '{}') } catch { }
  const lines = [
    `Type: ${payload?.project_type || 'unknown'}`,
    `Commands: ${(payload?.commands_run || []).join(', ') || 'none'}`,
    `Artifacts: ${(payload?.artifacts || []).length}`,
    `---`,
    payload?.log_preview || builderEvent.message || 'No log output.',
  ]
  if (builderEvent.event_type === 'phase_error') lines.unshift(`ERROR: ${builderEvent.message}`)

  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
      <button onClick={() => setOpen(o => !o)} className="flex items-center justify-between w-full text-left">
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-lime-400" />
          <p className="text-xs text-muted uppercase tracking-wider">Build & Run Log</p>
        </div>
        <span className="text-xs text-muted">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <pre className="mt-3 text-xs font-mono text-slate-300 whitespace-pre-wrap bg-surface-900 rounded p-3 max-h-80 overflow-y-auto">
          {lines.join('\n')}
        </pre>
      )}
    </div>
  )
}

function BuildProgress({ phase, status }: { phase: string | null; status: string }) {
  if (!phase || status === 'completed') return null
  const steps = ['architecting','coding','designing','hardening','validating','building','testing']
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
          <span key={s} className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
            i < currentIdx ? 'bg-green-900/40 text-green-400'
            : i === currentIdx ? 'bg-lime-900/40 text-lime-400 animate-pulse'
            : 'bg-surface-700 text-muted'
          }`}>
            {s}
          </span>
        ))}
      </div>
    </div>
  )
}

function LaunchPanel({ build, files }: { build: Build; files: GeneratedFile[] }) {
  if (build.status !== 'completed') return null
  const hasHtml = files.some(f => f.file_name.toLowerCase().endsWith('.html'))
  const hasPackageJson = files.some(f => f.file_name.toLowerCase().endsWith('package.json'))
  const hasPy = files.some(f => f.file_name.toLowerCase().endsWith('.py'))
  const runnable = hasHtml || hasPackageJson || hasPy

  const handleLaunch = () => {
    if (!runnable || files.length === 0) return
    if (hasHtml) window.open(`/api/builds/${build.id}/serve/`, '_blank')
    else if (hasPackageJson) alert('Run: cd build/src && npm install && npm start')
    else if (hasPy) alert('Run: cd build/src && python app.py')
  }

  return (
    <div className="bg-surface-800 border border-accent-500/30 rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Play size={14} className="text-accent-400" />
        <span className="text-xs text-muted font-mono uppercase tracking-wider">Launch Application</span>
      </div>
      <p className="text-xs text-slate-300">
        {hasHtml ? 'Open the generated HTML application in your browser.'
          : hasPackageJson ? 'Start the Node.js server.'
          : hasPy ? 'Start the Python application.'
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

// ─── Main page ────────────────────────────────────────────────────────────────

export default function BuildDetail() {
  const { id } = useParams<{ id: string }>()
  const { build, setBuild, loading, refetch } = useBuild(id ?? null)
  const { events: wsEvents, connected } = useBuildEvents(id ?? null)
  const [files, setFiles] = useState<GeneratedFile[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [dirConfig, setDirConfig] = useState<BuildDirectoryConfig | null>(null)

  // Reset all local state when build ID changes (e.g. after rerun)
  useEffect(() => {
    setFiles([])
    setFindings([])
    setDirConfig(null)
  }, [id])

  const loadSideData = useCallback(async () => {
    if (!id) return
    try {
      const [fd, fn] = await Promise.all([buildsApi.files(id), buildsApi.findings(id)])
      setFiles(fd.files)
      setFindings(fn.findings)
    } catch { }
    try {
      const dc = await contextApi.getBuildDirectories(id)
      setDirConfig(dc)
    } catch { }
  }, [id])

  useEffect(() => { loadSideData() }, [loadSideData])

  useEffect(() => {
    if (!build || !['running', 'queued'].includes(build.status)) return
    const timer = setInterval(() => { refetch(); loadSideData() }, 3000)
    return () => clearInterval(timer)
  }, [build?.status, refetch, loadSideData])

  useEffect(() => {
    const last = wsEvents[wsEvents.length - 1] as WsEvent | undefined
    if (last && ['pipeline_complete', 'pipeline_error'].includes(last.event_type)) {
      refetch(); loadSideData()
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
              onClick={async () => { await buildsApi.cancel(build.id); refetch() }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 border border-red-700 rounded transition-colors"
            >
              <XCircle size={12} /> Cancel
            </button>
          )}
          <button
            onClick={async () => {
              try { await buildsApi.openFolder(build.id) }
              catch { alert('Could not open folder — check backend is running') }
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted hover:text-slate-200 border border-surface-600 rounded transition-colors"
            title="Open build output in Explorer"
          >
            <FolderSearch size={12} /> Open Folder
          </button>
          <button
            onClick={() => { refetch(); loadSideData() }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted hover:text-slate-200 border border-surface-600 rounded transition-colors"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>

      {/* Meta */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Stack',   value: build.stack_target },
          { label: 'Mode',    value: build.mode },
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

      {/* Phase timeline after completion */}
      {build.status === 'completed' && wsEvents.length > 0 && (
        <PhaseTimeline events={wsEvents} status={build.status} />
      )}

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
              { label: 'Source Dir',    value: dirConfig.source_dir },
              { label: 'Workspace Dir', value: dirConfig.workspace_dir },
              { label: 'Output Dir',    value: dirConfig.output_dir },
              { label: 'Final Output',  value: dirConfig.final_output_path },
            ].map(({ label, value }) => value ? (
              <div key={label}>
                <p className="text-xs text-muted mb-0.5">{label}</p>
                <p className="text-xs font-mono text-slate-300 truncate">{value}</p>
              </div>
            ) : null)}
            {dirConfig.files_written > 0 && (
              <div className="flex items-center gap-3 col-span-full">
                <div className="flex items-center gap-1.5">
                  <FileText size={12} className="text-teal-400" />
                  <span className="text-xs text-teal-400 font-mono">{dirConfig.files_written} files written to output</span>
                </div>
                <button
                  onClick={async () => {
                    try { await buildsApi.openFolder(build.id) }
                    catch { alert('Could not open folder') }
                  }}
                  className="flex items-center gap-1 text-xs text-accent-400 hover:text-accent-300 border border-accent-500/30 hover:border-accent-500/60 px-2 py-0.5 rounded transition-colors"
                >
                  <FolderSearch size={10} /> Open in Explorer
                </button>
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

      {/* Live preview (HTML builds only) */}
      <PreviewPanel build={build} files={files} />

      {/* Refine with AI */}
      <RefinePanel build={build} files={files} />

      {/* Launch application */}
      <LaunchPanel build={build} files={files} />

      {/* Retry diff (only when retries happened) */}
      {build.retry_count > 0 && <DiffPanel files={files} />}

      {/* Files */}
      <FilesViewer files={files} />

      {/* Findings */}
      <FindingsPanel findings={findings} />
    </div>
  )
}
