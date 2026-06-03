import { useState, useEffect } from 'react'
import { Play, Loader2, Zap, Star, FolderOpen, ChevronDown, ChevronUp, Wifi, WifiOff } from 'lucide-react'
import type { CreateBuildPayload } from '../api/builds'
import type { BuildMode, ProjectContext } from '../types'
import { contextApi } from '../api/context'
import { ollamaApi } from '../api/settings'
import { brandKitsApi } from '../api/meta'
import type { BrandKit } from '../api/meta'

interface Props {
  onSubmit: (payload: CreateBuildPayload) => Promise<unknown>
}

function DirInput({ label, value, onChange, placeholder }: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder: string
}) {
  return (
    <div>
      <label className="block text-xs text-muted mb-1">{label}</label>
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 bg-surface-700 border border-surface-500 rounded px-3 py-2 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500 font-mono"
        />
      </div>
    </div>
  )
}

export default function BuildSubmitForm({ onSubmit }: Props) {
  const [projectName, setProjectName] = useState('')
  const [requirement, setRequirement] = useState('')
  const [mode, setMode] = useState<BuildMode>('fast')
  const [stackTarget, setStackTarget] = useState('auto')
  const [brandKit, setBrandKit] = useState('')
  const [brandKits, setBrandKits] = useState<BrandKit[]>([])
  const [sourceDir, setSourceDir] = useState('')
  const [workspaceDir, setWorkspaceDir] = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [selectedContext, setSelectedContext] = useState('')
  const [contexts, setContexts] = useState<ProjectContext[]>([])
  const [showDirs, setShowDirs] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ollamaOk, setOllamaOk] = useState<boolean | null>(null)

  useEffect(() => {
    contextApi.list().then(setContexts).catch(() => {})
    brandKitsApi.list().then(setBrandKits).catch(() => {})
    // Check Ollama health on mount and every 10s
    const check = () => {
      ollamaApi.health().then(r => setOllamaOk(r.connected)).catch(() => setOllamaOk(false))
    }
    check()
    const timer = setInterval(check, 10000)
    return () => clearInterval(timer)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!projectName.trim() || !requirement.trim()) return
    setSubmitting(true)
    setError(null)
    const payload: CreateBuildPayload = {
      project_name: projectName.trim(),
      requirement: requirement.trim(),
      stack_target: stackTarget,
      mode,
    }
    if (selectedContext) payload.project_context_id = selectedContext
    if (brandKit) payload.brand_kit = brandKit
    if (sourceDir.trim()) payload.source_dir = sourceDir.trim()
    if (workspaceDir.trim()) payload.workspace_dir = workspaceDir.trim()
    if (outputDir.trim()) payload.output_dir = outputDir.trim()
    try {
      await onSubmit(payload)
      setProjectName('')
      setRequirement('')
      setMode('fast')
      setStackTarget('auto')
      setBrandKit('')
      setSourceDir('')
      setWorkspaceDir('')
      setOutputDir('')
      setSelectedContext('')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-surface-800 border border-surface-600 rounded-lg p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">New Build</h2>
        <div className="flex items-center gap-2">
          {ollamaOk === false && (
            <span className="flex items-center gap-1 text-xs text-red-400 bg-red-900/30 px-2 py-0.5 rounded">
              <WifiOff size={12} /> LLM unreachable
            </span>
          )}
          {ollamaOk === true && (
            <span className="flex items-center gap-1 text-xs text-green-400 bg-green-900/30 px-2 py-0.5 rounded">
              <Wifi size={12} /> LLM ready
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>
      )}

      <div>
        <label className="block text-xs text-muted mb-1">Project Name</label>
        <input
          type="text"
          value={projectName}
          onChange={e => setProjectName(e.target.value)}
          placeholder="my-expense-tracker"
          required
          className="w-full bg-surface-700 border border-surface-500 rounded px-3 py-2 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500"
        />
      </div>

      <div>
        <label className="block text-xs text-muted mb-1">What do you want to build?</label>
        <textarea
          value={requirement}
          onChange={e => setRequirement(e.target.value)}
          placeholder="Describe your idea in plain language. The AI will figure out the best technology stack and architecture…"
          required
          rows={5}
          className="w-full bg-surface-700 border border-surface-500 rounded px-3 py-2 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500 resize-none"
        />
      </div>

      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {([['fast', 'Quick Build', Zap, 'Faster, good for prototyping'], ['quality', 'Quality Build', Star, 'Slower, more thorough']] as const).map(
            ([val, label, Icon, desc]) => (
              <button
                key={val}
                type="button"
                onClick={() => setMode(val as BuildMode)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-colors ${
                  mode === val
                    ? 'bg-accent-500 border-accent-500 text-white'
                    : 'border-surface-500 text-muted hover:text-slate-200 hover:border-surface-400'
                }`}
                title={desc}
              >
                <Icon size={12} />
                {label}
              </button>
            )
          )}
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <label className="text-xs text-muted whitespace-nowrap">Stack</label>
            <select
              value={stackTarget}
              onChange={e => setStackTarget(e.target.value)}
              className="bg-surface-700 border border-surface-500 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-accent-500 cursor-pointer"
            >
              <option value="auto">Auto-detect</option>
              <option value="html5">HTML5 / Vanilla</option>
              <option value="react">React</option>
              <option value="vue">Vue</option>
              <option value="nodejs">Node.js</option>
              <option value="python">Python</option>
              <option value="fastapi">FastAPI</option>
            </select>
          </div>

          {brandKits.length > 0 && (
            <div className="flex items-center gap-1.5">
              <label className="text-xs text-muted whitespace-nowrap">Brand</label>
              <select
                value={brandKit}
                onChange={e => setBrandKit(e.target.value)}
                title="Apply an offline brand kit (colors, fonts, voice, logo)"
                className="bg-surface-700 border border-surface-500 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-accent-500 cursor-pointer"
              >
                <option value="">None</option>
                {brandKits.map(k => <option key={k.slug} value={k.slug}>{k.name} — {k.industry}</option>)}
              </select>
              {brandKit && (() => {
                const k = brandKits.find(b => b.slug === brandKit)
                return k ? <span className="inline-flex gap-0.5" title={k.tagline}>
                  <span className="w-3 h-3 rounded-sm border border-surface-500" style={{ background: k.primary }} />
                  <span className="w-3 h-3 rounded-sm border border-surface-500" style={{ background: k.accent }} />
                </span> : null
              })()}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="flex items-center gap-2 px-4 py-2 bg-accent-500 hover:bg-accent-400 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded transition-colors"
          >
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {submitting ? 'Queuing...' : 'Start Build'}
          </button>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setShowDirs(s => !s)}
        className="flex items-center gap-1.5 text-xs text-muted hover:text-slate-200 transition-colors mt-2"
      >
        <FolderOpen size={12} />
        {showDirs ? 'Hide' : 'Advanced'} directories & context
        {showDirs ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {showDirs && (
        <div className="space-y-3 pt-1 border-t border-surface-600">
          {contexts.length > 0 && (
            <div>
              <label className="block text-xs text-muted mb-1">Project Context (optional)</label>
              <select
                value={selectedContext}
                onChange={e => setSelectedContext(e.target.value)}
                className="w-full bg-surface-700 border border-surface-500 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-accent-500 cursor-pointer"
              >
                <option value="">— None —</option>
                {contexts.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          )}
          <DirInput
            label="Source Directory (optional)"
            value={sourceDir}
            onChange={setSourceDir}
            placeholder="C:\\my-project  — existing code the AI can read"
          />
          <DirInput
            label="Workspace Directory (optional)"
            value={workspaceDir}
            onChange={setWorkspaceDir}
            placeholder="Where build artifacts are staged — defaults to system setting"
          />
          <DirInput
            label="Output Directory (optional)"
            value={outputDir}
            onChange={setOutputDir}
            placeholder="Where final files are copied on completion"
          />
        </div>
      )}
    </form>
  )
}
