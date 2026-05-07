import { clsx } from 'clsx'
import type { Finding } from '../types'

interface Props {
  findings: Finding[]
}

const SEVERITY_CONFIG = {
  high:   { cls: 'bg-red-900/40 border-red-800 text-red-300',    label: 'HIGH' },
  medium: { cls: 'bg-orange-900/40 border-orange-800 text-orange-300', label: 'MED' },
  low:    { cls: 'bg-yellow-900/30 border-yellow-800 text-yellow-300', label: 'LOW' },
}

export default function FindingsPanel({ findings }: Props) {
  if (findings.length === 0) {
    return (
      <div className="bg-surface-800 border border-surface-600 rounded-lg p-4 text-center text-muted text-sm font-mono">
        No findings.
      </div>
    )
  }

  const counts = findings.reduce((acc, f) => {
    acc[f.severity] = (acc[f.severity] ?? 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="bg-surface-800 border border-surface-600 rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-surface-600 flex items-center justify-between">
        <span className="text-xs font-mono font-semibold text-muted uppercase tracking-wider">
          Findings ({findings.length})
        </span>
        <div className="flex gap-2">
          {(['high', 'medium', 'low'] as const).map(s => counts[s] ? (
            <span key={s} className={clsx('text-xs font-mono px-1.5 py-0.5 rounded border', SEVERITY_CONFIG[s].cls)}>
              {counts[s]} {SEVERITY_CONFIG[s].label}
            </span>
          ) : null)}
        </div>
      </div>
      <div className="divide-y divide-surface-700 max-h-72 overflow-y-auto">
        {findings.map(f => {
          const cfg = SEVERITY_CONFIG[f.severity as keyof typeof SEVERITY_CONFIG] ?? SEVERITY_CONFIG.low
          return (
            <div key={f.id} className="px-3 py-3">
              <div className="flex items-start gap-2 mb-1">
                <span className={clsx('text-xs font-mono font-bold px-1.5 rounded', cfg.cls)}>{cfg.label}</span>
                <span className="text-xs font-semibold text-slate-200">{f.category}</span>
                {f.file_path && (
                  <span className="text-xs text-muted font-mono ml-auto flex-shrink-0 truncate max-w-xs">
                    {f.file_path}{f.line_number ? `:${f.line_number}` : ''}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-300 mb-1">{f.description}</p>
              {f.remediation && (
                <p className="text-xs text-teal-400 font-mono">→ {f.remediation}</p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
