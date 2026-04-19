import { useCallback, useEffect, useState } from 'react'
import * as api from '../lib/api'
import type { SessionListItem } from '../lib/types'

interface UseSessions {
  sessions: SessionListItem[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

export function useSessions(): UseSessions {
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(() => {
    setIsLoading(true)
    setError(null)
    api
      .listSessions()
      .then((res) => setSessions(res.items))
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Failed to load sessions'),
      )
      .finally(() => setIsLoading(false))
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { sessions, isLoading, error, refetch }
}
