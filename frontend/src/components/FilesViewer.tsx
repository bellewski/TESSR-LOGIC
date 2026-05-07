import { useState } from 'react'
import { FileText, ChevronRight, Copy, ExternalLink, FolderOpen, Check } from 'lucide-react'
import { buildsApi } from '../api/builds'
import type { GeneratedFile } from '../types'

interface Props {
  files: GeneratedFile[]
}

function formatBytes(b: number) {
  if (b < 1024) return `${b}B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}KB`
  return `${(b / (1024 * 1024)).toFixed(1)}MB`
}

function parentDir(path: string): string {
  const i = path.lastIndexOf('\\')
  if (i > 0) return path.slice(0, i)
  const j = path.lastIndexOf('/')
  if (j > 0) return path.slice(0, j)
  return path
}

function FilePathBar({ file }: { file: GeneratedFile }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(file.file_path)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* ignore */ }
  }

  const openFolder = () => {
    const dir = parentDir(file.file_path)
    // Try vscode:// protocol first, then file://
    window.open(`vscode://file/${dir}`, '_blank')
  }

  return (
    <div className="flex items-center gap-2 mb-2 flex-wrap">
      <span className="text-xs font-mono text-slate-400 truncate flex-1" title={file.file_path}>
        {file.file_path}
      </span>
      <button
        onClick={copy}
        className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-surface-700 hover:bg-surface-600 text-muted hover:text-slate-200 transition-colors border border-surface-500"
        title="Copy full path"
      >
        {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
        {copied ? 'Copied' : 'Copy'}
      </button>
      <button
        onClick={openFolder}
        className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-surface-700 hover:bg-surface-600 text-muted hover:text-slate-200 transition-colors border border-surface-500"
        title="Open folder in VS Code"
      >
        <FolderOpen size={12} />
        Open
      </button>
      <span className={`text-xs font-mono ${PHASE_COLOR[file.phase] ?? 'text-muted'}`}>
        [{file.phase}]
      </span>
      <span className="text-xs text-muted">{formatBytes(file.size_bytes)}</span>
    </div>
  )
}

const PHASE_COLOR: Record<string, string> = {
  architecting: 'text-purple-400',
  coding: 'text-cyan-400',
  hardening: 'text-orange-400',
}

export default function FilesViewer({ files }: Props) {
  const [selected, setSelected] = useState<GeneratedFile | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const openFile = async (f: GeneratedFile) => {
    setSelected(f)
    setLoading(true)
    setContent(null)
    try {
      const text = await buildsApi.fileContent(f.file_path)
      setContent(text)
    } catch {
      setContent(f.content_preview ?? '(preview unavailable)')
    } finally {
      setLoading(false)
    }
  }

  if (files.length === 0) {
    return (
      <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 text-center text-muted text-sm">
        No generated files yet.
      </div>
    )
  }

  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-surface-600">
        <span className="text-xs font-mono font-semibold text-muted uppercase tracking-wider">
          Generated Files ({files.length})
        </span>
      </div>
      <div className="flex divide-x divide-surface-600" style={{ minHeight: 240 }}>
        {/* File list */}
        <div className="w-56 flex-shrink-0 overflow-y-auto max-h-72">
          {files.map(f => (
            <button
              key={f.id}
              onClick={() => openFile(f)}
              className={`w-full text-left px-3 py-2 flex items-center gap-2 text-xs hover:bg-surface-700 transition-colors ${
                selected?.id === f.id ? 'bg-surface-700 text-accent-400' : 'text-slate-300'
              }`}
            >
              <FileText size={12} className="flex-shrink-0 text-muted" />
              <span className="truncate font-mono flex-1">{f.file_name}</span>
              <ChevronRight size={10} className="text-muted flex-shrink-0" />
            </button>
          ))}
        </div>

        {/* Content pane */}
        <div className="flex-1 overflow-auto max-h-72 p-3 bg-surface-900">
          {!selected && (
            <p className="text-muted text-xs font-mono italic">Select a file to view its contents.</p>
          )}
          {selected && loading && (
            <p className="text-muted text-xs font-mono italic">Loading...</p>
          )}
          {selected && !loading && content !== null && (
            <>
              <FilePathBar file={selected} />
              <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap break-all">{content}</pre>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
