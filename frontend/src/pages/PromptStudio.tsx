import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Loader2, Save, BookOpen, Play, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import { promptsApi } from '../api/prompts'
import { contextApi } from '../api/context'
import type { ChatMessage, PromptFields, PromptTemplate, ProjectContext, AgentPreview } from '../types'
import { useNavigate } from 'react-router-dom'
import { buildsApi } from '../api/builds'

const FIELD_LABELS: Record<keyof PromptFields, string> = {
  what_to_build:       'What to Build',
  target_audience:     'Target Audience',
  platform_type:       'Platform Type',
  key_features:        'Key Features',
  constraints:         'Constraints',
  tech_stack:          'Tech Stack',
  security_sensitivity:'Security Sensitivity',
  output_format:       'Output Format',
}

const PLATFORM_OPTIONS = ['web', 'mobile', 'desktop', 'CLI', 'API', 'automation', 'library', 'other']
const SECURITY_OPTIONS = ['low', 'medium', 'high']

// ── Sub-components ───────────────────────────────────────────────────────────

function ChatPanel({ messages, sending, onSend }: {
  messages: ChatMessage[]
  sending: boolean
  onSend: (msg: string) => void
}) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  const submit = () => {
    const t = input.trim()
    if (!t || sending) return
    setInput('')
    onSend(t)
  }

  return (
    <div className="flex flex-col h-full bg-surface-900 border border-surface-600 rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-surface-600 text-xs font-mono font-semibold text-muted uppercase tracking-wider">
        Requirement Chatbot
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-muted text-xs italic mt-4 text-center">
            Describe your idea and I'll help you shape it into a build prompt.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
              m.role === 'user'
                ? 'bg-accent-600 text-white'
                : 'bg-surface-700 text-slate-200'
            }`}>
              {m.content}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-surface-700 rounded-lg px-3 py-2 flex items-center gap-2 text-muted text-xs">
              <Loader2 size={12} className="animate-spin" /> Thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="p-2 border-t border-surface-600 flex gap-2">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
          rows={2}
          placeholder="Describe what you want to build… (Enter to send)"
          className="flex-1 bg-surface-700 border border-surface-500 rounded px-3 py-2 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500 resize-none font-mono"
        />
        <button
          onClick={submit}
          disabled={sending || !input.trim()}
          className="self-end p-2 bg-accent-500 hover:bg-accent-400 disabled:opacity-40 text-white rounded transition-colors"
        >
          {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </button>
      </div>
    </div>
  )
}

function StructuredForm({ fields, onChange }: {
  fields: PromptFields
  onChange: (f: PromptFields) => void
}) {
  const set = (key: keyof PromptFields, val: string) => onChange({ ...fields, [key]: val })

  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 space-y-3 overflow-y-auto">
      <div className="text-xs font-mono font-semibold text-muted uppercase tracking-wider mb-1">
        Structured Fields
      </div>
      <div>
        <label className="block text-xs text-muted mb-1">What to Build</label>
        <input
          value={fields.what_to_build || ''}
          onChange={e => set('what_to_build', e.target.value)}
          placeholder="A REST API for tracking expenses…"
          className="w-full bg-surface-700 border border-surface-500 rounded px-2.5 py-1.5 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500"
        />
      </div>
      <div>
        <label className="block text-xs text-muted mb-1">Target Audience</label>
        <input
          value={fields.target_audience || ''}
          onChange={e => set('target_audience', e.target.value)}
          placeholder="Small business owners"
          className="w-full bg-surface-700 border border-surface-500 rounded px-2.5 py-1.5 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500"
        />
      </div>
      <div>
        <label className="block text-xs text-muted mb-1">Platform Type</label>
        <div className="flex flex-wrap gap-1.5">
          {PLATFORM_OPTIONS.map(p => (
            <button key={p} onClick={() => set('platform_type', p)}
              className={`px-2 py-0.5 rounded text-xs font-mono border transition-colors ${
                fields.platform_type === p
                  ? 'bg-accent-500 border-accent-500 text-white'
                  : 'border-surface-500 text-muted hover:border-accent-500 hover:text-slate-200'
              }`}>{p}</button>
          ))}
        </div>
      </div>
      <div>
        <label className="block text-xs text-muted mb-1">Key Features</label>
        <textarea
          value={fields.key_features || ''}
          onChange={e => set('key_features', e.target.value)}
          rows={2}
          placeholder="Auth, CRUD, export to CSV…"
          className="w-full bg-surface-700 border border-surface-500 rounded px-2.5 py-1.5 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500 resize-none"
        />
      </div>
      <div>
        <label className="block text-xs text-muted mb-1">Tech Stack</label>
        <input
          value={fields.tech_stack || ''}
          onChange={e => set('tech_stack', e.target.value)}
          placeholder="FastAPI + React + SQLite"
          className="w-full bg-surface-700 border border-surface-500 rounded px-2.5 py-1.5 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500"
        />
      </div>
      <div>
        <label className="block text-xs text-muted mb-1">Constraints</label>
        <input
          value={fields.constraints || ''}
          onChange={e => set('constraints', e.target.value)}
          placeholder="No cloud services, runs on Raspberry Pi…"
          className="w-full bg-surface-700 border border-surface-500 rounded px-2.5 py-1.5 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500"
        />
      </div>
      <div>
        <label className="block text-xs text-muted mb-1">Security Sensitivity</label>
        <div className="flex gap-2">
          {SECURITY_OPTIONS.map(s => (
            <button key={s} onClick={() => set('security_sensitivity', s)}
              className={`px-3 py-0.5 rounded text-xs font-mono border transition-colors ${
                fields.security_sensitivity === s
                  ? 'bg-accent-500 border-accent-500 text-white'
                  : 'border-surface-500 text-muted hover:border-accent-500'
              }`}>{s}</button>
          ))}
        </div>
      </div>
      <div>
        <label className="block text-xs text-muted mb-1">Output Format</label>
        <input
          value={fields.output_format || ''}
          onChange={e => set('output_format', e.target.value)}
          placeholder="files / deployed app / library"
          className="w-full bg-surface-700 border border-surface-500 rounded px-2.5 py-1.5 text-sm text-slate-200 placeholder-muted focus:outline-none focus:border-accent-500"
        />
      </div>
    </div>
  )
}

function AgentPreviewCard({ label, preview }: { label: string; preview: AgentPreview }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-surface-600 rounded bg-surface-800 text-xs">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-surface-700 transition-colors"
      >
        <span className="font-mono font-semibold text-accent-300">{preview.agent}</span>
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-1.5 text-slate-400">
          <p>{preview.input_summary}</p>
          {preview.stack && <p><span className="text-muted">Stack:</span> {preview.stack}</p>}
          {preview.note && <p className="text-yellow-400">{preview.note}</p>}
          {preview.prompt_preview && (
            <pre className="text-slate-500 whitespace-pre-wrap break-all text-xs bg-surface-900 rounded p-2 mt-1">
              {preview.prompt_preview}
            </pre>
          )}
          {preview.checks && (
            <div>
              <span className="text-muted">Checks:</span>{' '}
              {preview.checks.map(c => <code key={c} className="mx-0.5 text-orange-300">{c}</code>)}
            </div>
          )}
          {preview.retry_budget != null && (
            <p><span className="text-muted">Retry budget:</span> {preview.retry_budget}</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function PromptStudio() {
  const navigate = useNavigate()

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [fields, setFields] = useState<PromptFields>({})
  const [sending, setSending] = useState(false)
  const [finalPrompt, setFinalPrompt] = useState('')
  const [agentPreviews, setAgentPreviews] = useState<Record<string, AgentPreview>>({})
  const [generating, setGenerating] = useState(false)
  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [saving, setSaving] = useState(false)
  const [selectedTemplate, setSelectedTemplate] = useState<string>('')
  const [contexts, setContexts] = useState<ProjectContext[]>([])
  const [selectedContext, setSelectedContext] = useState<string>('')
  const [sendingToPipeline, setSendingToPipeline] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load templates and contexts on mount
  useEffect(() => {
    promptsApi.listTemplates().then(setTemplates).catch(() => {})
    contextApi.list().then(setContexts).catch(() => {})
  }, [])

  const handleChat = useCallback(async (userMsg: string) => {
    const newMessages: ChatMessage[] = [...messages, { role: 'user', content: userMsg }]
    setMessages(newMessages)
    setSending(true)
    setError(null)
    try {
      const result = await promptsApi.chat(newMessages, fields)
      setMessages(prev => [...prev, { role: 'assistant', content: result.reply }])
      setFields(result.updated_fields || fields)
    } catch (e) {
      setError('Chat failed — is Ollama running?')
    } finally {
      setSending(false)
    }
  }, [messages, fields])

  const handleGenerate = async () => {
    setGenerating(true)
    setError(null)
    try {
      const ctx = contexts.find(c => c.id === selectedContext)
      const result = await promptsApi.generate(fields, ctx?.context_summary ?? undefined)
      setFinalPrompt(result.final_prompt)
      setAgentPreviews(result.agent_previews)
    } catch {
      setError('Generation failed — is Ollama running?')
    } finally {
      setGenerating(false)
    }
  }

  const handleSaveTemplate = async () => {
    setSaving(true)
    try {
      const name = `Template ${new Date().toLocaleString()}`
      const history = JSON.stringify(messages)
      await promptsApi.createTemplate({
        name,
        ...fields,
        final_prompt: finalPrompt || null,
        conversation_history: history,
      })
      const updated = await promptsApi.listTemplates()
      setTemplates(updated)
    } catch {
      setError('Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleLoadTemplate = async (id: string) => {
    if (!id) return
    setSelectedTemplate(id)
    const tpl = await promptsApi.getTemplate(id)
    setFields({
      what_to_build:       tpl.what_to_build ?? undefined,
      target_audience:     tpl.target_audience ?? undefined,
      platform_type:       tpl.platform_type ?? undefined,
      key_features:        tpl.key_features ?? undefined,
      constraints:         tpl.constraints ?? undefined,
      tech_stack:          tpl.tech_stack ?? undefined,
      security_sensitivity:tpl.security_sensitivity ?? undefined,
      output_format:       tpl.output_format ?? undefined,
    })
    if (tpl.final_prompt) setFinalPrompt(tpl.final_prompt)
    if (tpl.conversation_history) {
      try { setMessages(JSON.parse(tpl.conversation_history)) } catch {}
    }
  }

  const handleSendToPipeline = async () => {
    if (!finalPrompt && !fields.what_to_build) {
      setError('Generate a prompt first.')
      return
    }
    setSendingToPipeline(true)
    setError(null)
    try {
      const ctx = contexts.find(c => c.id === selectedContext)
      const requirement = finalPrompt || fields.what_to_build || ''
      const build = await buildsApi.create({
        project_name: fields.what_to_build?.slice(0, 60) || 'Untitled Build',
        requirement,
        stack_target: fields.tech_stack || 'auto',
        mode: 'fast',
        project_context_id: selectedContext || undefined,
        source_dir: ctx?.source_dir ?? undefined,
        workspace_dir: ctx?.workspace_dir ?? undefined,
        output_dir: ctx?.output_dir ?? undefined,
      })
      navigate(`/builds/${build.id}`)
    } catch (e) {
      setError('Failed to create build')
    } finally {
      setSendingToPipeline(false)
    }
  }

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-surface-700 flex-shrink-0">
        <div>
          <h1 className="text-base font-semibold text-slate-200">Prompt Studio</h1>
          <p className="text-xs text-muted mt-0.5">Refine your idea → generate a build prompt → send to pipeline</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Load template */}
          {templates.length > 0 && (
            <select
              value={selectedTemplate}
              onChange={e => handleLoadTemplate(e.target.value)}
              className="bg-surface-700 border border-surface-500 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none"
            >
              <option value="">Load template…</option>
              {templates.map(t => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          )}
          {/* Project context selector */}
          <select
            value={selectedContext}
            onChange={e => setSelectedContext(e.target.value)}
            className="bg-surface-700 border border-surface-500 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none"
          >
            <option value="">No project context</option>
            {contexts.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <button
            onClick={handleSaveTemplate}
            disabled={saving}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-surface-500 rounded text-muted hover:text-slate-200 transition-colors disabled:opacity-40"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            Save
          </button>
          <button
            onClick={handleSendToPipeline}
            disabled={sendingToPipeline}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-green-600 hover:bg-green-500 disabled:opacity-40 text-white rounded transition-colors font-medium"
          >
            {sendingToPipeline ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            Send to Pipeline
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">
          {error}
        </div>
      )}

      {/* Three-column layout */}
      <div className="flex flex-1 overflow-hidden gap-0">
        {/* Left: Chat */}
        <div className="flex flex-col w-[34%] min-w-0 p-3 overflow-hidden">
          <ChatPanel messages={messages} sending={sending} onSend={handleChat} />
        </div>

        {/* Middle: Structured form */}
        <div className="flex flex-col w-[28%] min-w-0 p-3 overflow-y-auto">
          <StructuredForm fields={fields} onChange={setFields} />
        </div>

        {/* Right: Generated prompt + agent previews */}
        <div className="flex flex-col w-[38%] min-w-0 p-3 space-y-3 overflow-y-auto">
          {/* Generate button */}
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center justify-center gap-2 w-full py-2 bg-accent-500 hover:bg-accent-400 disabled:opacity-40 text-white text-sm font-medium rounded transition-colors"
          >
            {generating ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {generating ? 'Generating…' : 'Generate Final Prompt'}
          </button>

          {/* Final prompt preview */}
          <div className="bg-surface-900 border border-surface-600 rounded-lg overflow-hidden flex flex-col flex-1 min-h-48">
            <div className="px-3 py-2 border-b border-surface-600 flex items-center justify-between">
              <span className="text-xs font-mono font-semibold text-muted uppercase tracking-wider">Final Build Prompt</span>
              <BookOpen size={12} className="text-muted" />
            </div>
            <textarea
              value={finalPrompt}
              onChange={e => setFinalPrompt(e.target.value)}
              placeholder="Click 'Generate Final Prompt' or edit manually…"
              className="flex-1 bg-transparent p-3 text-sm text-slate-300 font-mono resize-none focus:outline-none placeholder-surface-500"
            />
          </div>

          {/* Agent handoff previews */}
          {Object.keys(agentPreviews).length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-mono text-muted uppercase tracking-wider">Agent Handoff Previews</p>
              {Object.entries(agentPreviews).map(([key, preview]) => (
                <AgentPreviewCard key={key} label={key} preview={preview as AgentPreview} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
