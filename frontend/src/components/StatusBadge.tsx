import { clsx } from 'clsx'
import type { BuildStatus } from '../types'

interface Props { status: BuildStatus; className?: string }

const CONFIG: Record<BuildStatus, { label: string; cls: string }> = {
  created:   { label: 'Created',   cls: 'bg-slate-700 text-slate-300' },
  queued:    { label: 'Queued',    cls: 'bg-yellow-900/60 text-yellow-300' },
  running:   { label: 'Running',   cls: 'bg-blue-900/60 text-blue-300 animate-pulse' },
  completed: { label: 'Completed', cls: 'bg-green-900/60 text-green-300' },
  failed:    { label: 'Failed',    cls: 'bg-red-900/60 text-red-400' },
}

export default function StatusBadge({ status, className }: Props) {
  const { label, cls } = CONFIG[status] ?? CONFIG.created
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold font-mono', cls, className)}>
      {label}
    </span>
  )
}
