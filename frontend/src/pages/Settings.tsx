import { useEffect, useState } from 'react'
import { Save, Loader2, RefreshCw } from 'lucide-react'
import { settingsApi, ollamaApi } from '../api/settings'
import type { AppSettings } from '../types'

export default function Settings() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [ollamaStatus, setOllamaStatus] = useState<string>('checking')

  useEffect(() => {
    settingsApi.get().then(setSettings).finally(() => setLoading(false))
    ollamaApi.health().then(r => setOllamaStatus(r.connected ? 'connected' : 'unreachable')).catch(() => setOllamaStatus('unreachable'))
    ollamaApi.models().then(r => setModels(r.models)).catch(() => setModels([]))
  }, [])

  const handleSave = async () => {
    if (!settings) return
    setSaving(true)
    setError(null)
    try {
      const updated = await settingsApi.update(settings)
      setSettings(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const refreshModels = () => {
    setOllamaStatus('checking')
    ollamaApi.health().then(r => setOllamaStatus(r.connected ? 'connected' : 'unreachable')).catch(() => setOllamaStatus('unreachable'))
    ollamaApi.models().then(r => setModels(r.models)).catch(() => setModels([]))
  }

  if (loading) return <div className="flex-1 flex items-center justify-center text-muted font-mono text-sm">Loading...</div>
  if (!settings) return null

  const field = (label: string, key: keyof AppSettings, type: string = 'text') => (
    <div>
      <label className="block text-xs text-muted mb-1">{label}</label>
      <input
        type={type}
        value={String(settings[key])}
        onChange={e => setSettings(prev => prev ? { ...prev, [key]: type === 'number' ? Number(e.target.value) : e.target.value } : prev)}
        className="w-full bg-surface-700 border border-surface-500 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-accent-500 font-mono"
      />
    </div>
  )

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-2xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-200">Settings</h1>
        <p className="text-xs text-muted mt-0.5">Runtime configuration — stored in the database.</p>
      </div>

      {/* Ollama status */}
      <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">Ollama Runtime</h2>
          <div className="flex items-center gap-2">
            <span className={`text-xs font-mono ${ollamaStatus === 'connected' ? 'text-success' : ollamaStatus === 'checking' ? 'text-yellow-400' : 'text-danger'}`}>
              {ollamaStatus}
            </span>
            <button onClick={refreshModels} className="text-muted hover:text-slate-200 transition-colors">
              <RefreshCw size={12} />
            </button>
          </div>
        </div>
        {models.length > 0 && (
          <div>
            <p className="text-xs text-muted mb-1">Available models:</p>
            <div className="flex flex-wrap gap-1">
              {models.map(m => (
                <span key={m} className="text-xs font-mono px-2 py-0.5 bg-surface-700 text-slate-300 rounded">{m}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Settings form */}
      <div className="bg-surface-800 border border-surface-600 rounded-lg p-5 space-y-4">
        <h2 className="text-sm font-semibold text-slate-300">Configuration</h2>
        {field('Ollama Base URL', 'ollama_base_url')}
        {field('Fast Model', 'ollama_fast_model')}
        {field('Quality Model', 'ollama_quality_model')}
        {field('Timeout (seconds)', 'ollama_timeout', 'number')}
        {field('Workspace Path', 'workspace_path')}

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-accent-500 hover:bg-accent-400 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            {saved ? 'Saved!' : saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  )
}
