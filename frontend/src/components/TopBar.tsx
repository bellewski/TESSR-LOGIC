import { useEffect, useState } from 'react'
import { Circle } from 'lucide-react'
import { ollamaApi } from '../api/settings'
import { clsx } from 'clsx'

export default function TopBar() {
  const [ollamaOk, setOllamaOk] = useState<boolean | null>(null)

  useEffect(() => {
    ollamaApi.health()
      .then(r => setOllamaOk(r.connected))
      .catch(() => setOllamaOk(false))

    const id = setInterval(() => {
      ollamaApi.health()
        .then(r => setOllamaOk(r.connected))
        .catch(() => setOllamaOk(false))
    }, 30000)
    return () => clearInterval(id)
  }, [])

  return (
    <header className="h-11 flex items-center justify-between px-5 bg-surface-800 border-b border-surface-600 flex-shrink-0">
      <p className="text-xs text-muted font-mono">TESSR-LOGIC / Operator Console</p>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5 text-xs font-mono">
          <Circle
            size={8}
            className={clsx(
              'fill-current',
              ollamaOk === true  && 'text-success',
              ollamaOk === false && 'text-danger',
              ollamaOk === null  && 'text-muted'
            )}
          />
          <span className={clsx(
            ollamaOk === true  && 'text-success',
            ollamaOk === false && 'text-danger',
            ollamaOk === null  && 'text-muted'
          )}>
            Ollama {ollamaOk === true ? 'connected' : ollamaOk === false ? 'unreachable' : 'checking'}
          </span>
        </div>
      </div>
    </header>
  )
}
