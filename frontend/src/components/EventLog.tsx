import { useEffect, useRef } from 'react'
import { clsx } from 'clsx'
import type { WsEvent } from '../types'

interface Props {
  events: WsEvent[]
  connected: boolean
}

const EVENT_COLOR: Record<string, string> = {
  pipeline_start:    'text-accent-400',
  pipeline_complete: 'text-success',
  pipeline_error:    'text-danger',
  phase_start:       'text-purple-300',
  phase_complete:    'text-teal-300',
  phase_error:       'text-red-400',
  retry:             'text-yellow-400',
  validation_failed: 'text-orange-400',
  build_created:     'text-slate-400',
}

export default function EventLog({ events, connected }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  return (
    <div className="bg-surface-900 border border-surface-600 rounded-lg flex flex-col h-80">
      <div className="flex items-center justify-between px-3 py-2 border-b border-surface-600">
        <span className="text-xs font-mono font-semibold text-muted uppercase tracking-wider">Event Log</span>
        <div className="flex items-center gap-1.5">
          <span className={clsx('w-2 h-2 rounded-full', connected ? 'bg-success animate-pulse' : 'bg-muted')} />
          <span className="text-xs text-muted font-mono">{connected ? 'live' : 'offline'}</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3 font-mono text-xs space-y-0.5">
        {events.length === 0 && (
          <p className="text-muted italic">Waiting for events...</p>
        )}
        {events.map((ev, i) => (
          <div key={i} className="flex gap-2 leading-5">
            <span className="text-surface-500 flex-shrink-0 select-none">
              {new Date(ev.timestamp || '').toLocaleTimeString()}
            </span>
            {ev.phase && (
              <span className="text-muted flex-shrink-0">[{ev.phase}]</span>
            )}
            <span className={clsx('flex-1 break-all', EVENT_COLOR[ev.event_type] ?? 'text-slate-300')}>
              {ev.message}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
