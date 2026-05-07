import { clsx } from 'clsx'
import type { BuildPhase } from '../types'

interface Props { phase: BuildPhase | null | string; className?: string }

const CONFIG: Record<string, string> = {
  architecting: 'bg-purple-900/60 text-purple-300',
  coding:       'bg-cyan-900/60 text-cyan-300',
  designing:    'bg-indigo-900/60 text-indigo-300',
  hardening:    'bg-orange-900/60 text-orange-300',
  validating:   'bg-teal-900/60 text-teal-300',
  building:     'bg-lime-900/60 text-lime-300',
  testing:      'bg-pink-900/60 text-pink-300',
}

export default function PhasePill({ phase, className }: Props) {
  if (!phase) return null
  const cls = CONFIG[phase] ?? 'bg-slate-700 text-slate-300'
  return (
    <span className={clsx('phase-pill', cls, className)}>
      {phase}
    </span>
  )
}
