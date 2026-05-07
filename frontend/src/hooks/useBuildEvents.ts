import { useState, useEffect, useRef, useCallback } from 'react'
import type { WsEvent } from '../types'

const MAX_RECONNECT_ATTEMPTS = 10
const RECONNECT_BASE_MS = 1000

export function useBuildEvents(buildId: string | null) {
  const [events, setEvents] = useState<WsEvent[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearReconnect = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!buildId) {
      setEvents([])
      setConnected(false)
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsHost = window.location.hostname
    // In dev (Vite port 5173), connect directly to backend on 8000
    // In production (served from backend), use same port, or omit if default
    let wsPort = window.location.port === '5173' ? '8000' : window.location.port
    if (wsPort === '80' || wsPort === '443') wsPort = ''
    const portStr = wsPort ? `:${wsPort}` : ''
    const url = `${protocol}://${wsHost}${portStr}/ws/builds/${buildId}/events`

    const connect = () => {
      // Don't reconnect if component unmounted
      if (!buildId) return

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        attemptRef.current = 0
        setConnected(true)
      }

      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null

        // Exponential backoff reconnect
        if (attemptRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = RECONNECT_BASE_MS * Math.pow(1.5, attemptRef.current)
          attemptRef.current += 1
          timerRef.current = setTimeout(connect, delay)
        }
      }

      ws.onerror = (err) => {
        // Log for debugging but let onclose handle reconnect
        console.warn(`WebSocket error for build ${buildId}:`, err)
      }

      ws.onmessage = (msg) => {
        try {
          const event: WsEvent = JSON.parse(msg.data)
          if (event.event_type === 'ping') return
          setEvents(prev => [...prev, event])
        } catch {
          // ignore malformed messages
        }
      }
    }

    connect()

    return () => {
      clearReconnect()
      if (wsRef.current) {
        // Prevent onclose from triggering reconnect during unmount
        const ws = wsRef.current
        ws.onclose = null
        ws.onerror = null
        ws.close()
        wsRef.current = null
      }
      attemptRef.current = 0
      setConnected(false)
    }
  }, [buildId, clearReconnect])

  return { events, connected }
}
