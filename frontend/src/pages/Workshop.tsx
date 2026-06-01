import { useState, useEffect, useRef, useCallback } from 'react'
import { Wrench, Send, Loader2, RefreshCw, ExternalLink, Sparkles, FileCode } from 'lucide-react'
import { buildsApi } from '../api/builds'
import type { Build } from '../types'

interface ChatMsg {
  role: 'user' | 'assistant'
  text: string
  changed?: string[]
}

export default function Workshop() {
  const [builds, setBuilds] = useState<Build[]>([])
  const [buildId, setBuildId] = useState('')
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [previewKey, setPreviewKey] = useState(0)   // bump to reload the iframe
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Load completed projects
  useEffect(() => {
    buildsApi.list(0, 200).then(({ builds }) => {
      const done = builds.filter(b => b.status === 'completed' || b.status === 'failed')
      setBuilds(done)
      if (done.length && !buildId) setBuildId(done[0].id)
    }).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setMessages(buildId ? [{
      role: 'assistant',
      text: "Tell me what you'd like to change about this project — in plain English. " +
            "For example: \"make it look more professional with a purple theme,\" \"add a testimonials section,\" " +
            "or \"make the buttons bigger and rounded.\" I'll figure out which files to edit and do it for you.",
    }] : [])
  }, [buildId])

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy])

  const send = useCallback(async () => {
    const msg = input.trim()
    if (!msg || !buildId || busy) return
    setInput('')
    setMessages(m => [...m, { role: 'user', text: msg }])
    setBusy(true)
    try {
      const res = await buildsApi.workshopAssist(buildId, msg)
      setMessages(m => [...m, {
        role: 'assistant',
        text: res.summary || (res.applied ? 'Done.' : "I couldn't apply that — try being more specific."),
        changed: res.changed_files,
      }])
      if (res.applied) setPreviewKey(k => k + 1)  // reload preview to show changes
    } catch (e: any) {
      setMessages(m => [...m, {
        role: 'assistant',
        text: 'Something went wrong: ' + (e?.response?.data?.detail || e?.message || 'request failed') +
              ' (large changes can take a minute on the GPU — try again or be more specific).',
      }])
    }
    setBusy(false)
  }, [input, buildId, busy])

  const selected = builds.find(b => b.id === buildId)
  const previewSrc = buildId ? `/api/builds/${buildId}/serve/` : ''

  return (
    <div className="flex-1 overflow-hidden flex">
      {/* Left: chat assistant */}
      <div className="w-[440px] flex-shrink-0 border-r border-surface-700 flex flex-col">
        <div className="px-4 py-3 border-b border-surface-700 space-y-2">
          <div className="flex items-center gap-2">
            <Wrench size={16} className="text-accent-400" />
            <span className="text-sm font-mono font-semibold text-slate-200">Workshop — AI Editor</span>
          </div>
          <select
            value={buildId}
            onChange={e => setBuildId(e.target.value)}
            className="w-full bg-surface-900 border border-surface-600 rounded px-2 py-2 text-sm font-mono text-slate-200"
          >
            {builds.length === 0 && <option value="">No projects yet</option>}
            {builds.map(b => <option key={b.id} value={b.id}>{b.project_name}</option>)}
          </select>
          <p className="text-xs text-muted">Pick a project, then just describe the changes you want.</p>
        </div>

        {/* messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[90%] rounded-lg px-3 py-2 text-sm ${
                m.role === 'user'
                  ? 'bg-accent-500/20 text-slate-100 border border-accent-500/30'
                  : 'bg-surface-800 text-slate-300 border border-surface-600'
              }`}>
                {m.role === 'assistant' && (
                  <div className="flex items-center gap-1 text-accent-400 text-xs mb-1"><Sparkles size={11} /> Assistant</div>
                )}
                <div className="whitespace-pre-wrap leading-relaxed">{m.text}</div>
                {m.changed && m.changed.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-surface-600 text-xs text-muted">
                    <span className="text-teal-400">✓ updated:</span>{' '}
                    {m.changed.map(f => (
                      <span key={f} className="inline-flex items-center gap-1 mr-2 font-mono">
                        <FileCode size={10} />{f}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex justify-start">
              <div className="bg-surface-800 border border-surface-600 rounded-lg px-3 py-2 text-sm text-muted flex items-center gap-2">
                <Loader2 size={13} className="animate-spin text-accent-400" /> Working on it… (the GPU is editing your files)
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* input */}
        <div className="border-t border-surface-700 p-3">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="Describe a change… e.g. 'make it more professional with a deep indigo theme and a bigger hero'"
              rows={2}
              disabled={!buildId || busy}
              className="flex-1 bg-surface-900 border border-surface-600 rounded px-3 py-2 text-sm text-slate-200 resize-none disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={!buildId || busy || !input.trim()}
              className="flex-shrink-0 bg-accent-500/20 text-accent-300 border border-accent-500/40 rounded px-3 py-2.5 disabled:opacity-40 hover:bg-accent-500/30"
              title="Send"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
          <p className="text-xs text-surface-500 mt-1">Enter to send · Shift+Enter for new line</p>
        </div>
      </div>

      {/* Right: live preview */}
      <div className="flex-1 flex flex-col">
        <div className="flex items-center justify-between px-4 py-2 border-b border-surface-700">
          <span className="text-xs font-mono text-muted uppercase tracking-wider">Live Preview {selected ? `— ${selected.project_name}` : ''}</span>
          <div className="flex items-center gap-2">
            <button onClick={() => setPreviewKey(k => k + 1)} className="text-muted hover:text-slate-200" title="Reload preview"><RefreshCw size={13} /></button>
            {previewSrc && (
              <a href={previewSrc} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-accent-400 hover:text-accent-300 border border-accent-500/30 px-2 py-1 rounded">
                <ExternalLink size={11} /> Open
              </a>
            )}
          </div>
        </div>
        {previewSrc ? (
          <iframe
            key={previewKey}
            src={previewSrc}
            className="flex-1 w-full bg-white"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            title="Project preview"
          />
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted text-sm font-mono">
            Select a project to preview it here.
          </div>
        )}
      </div>
    </div>
  )
}
