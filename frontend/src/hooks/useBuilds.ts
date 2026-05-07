import { useState, useEffect, useCallback } from 'react'
import { buildsApi, type CreateBuildPayload } from '../api/builds'
import type { Build } from '../types'

export function useBuilds() {
  const [builds, setBuilds] = useState<Build[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await buildsApi.list()
      setBuilds(data.builds)
      setTotal(data.total)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load builds')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const createBuild = useCallback(async (payload: CreateBuildPayload) => {
    const build = await buildsApi.create(payload)
    setBuilds(prev => [build, ...prev])
    setTotal(prev => prev + 1)
    return build
  }, [])

  return { builds, total, loading, error, refetch: fetch, createBuild }
}

export function useBuild(id: string | null) {
  const [build, setBuild] = useState<Build | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const data = await buildsApi.get(id)
      setBuild(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load build')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { fetch() }, [fetch])

  // Poll every 3s while build is running or queued to keep phase/status current
  useEffect(() => {
    if (!build || (build.status !== 'running' && build.status !== 'queued')) return
    const timer = setInterval(fetch, 3000)
    return () => clearInterval(timer)
  }, [build?.status, build?.current_phase, fetch])

  return { build, setBuild, loading, error, refetch: fetch }
}
