// WebSocket hook with auto-reconnect (max 3 attempts, exponential backoff).
// Auth: token passed as ?token= query param.

import { useCallback, useEffect, useRef, useState } from 'react'
import { getToken } from '../lib/api'
import type { StreamFrame } from '../lib/types'

type Status = 'idle' | 'connecting' | 'connected' | 'done' | 'error'

const MAX_RETRIES = 3
const BASE_DELAY_MS = 1000

interface NexusStream {
  frames: StreamFrame[]
  status: Status
  connect: (sessionId: string, goal: string) => void
  disconnect: () => void
}

export function useNexusStream(): NexusStream {
  const [frames, setFrames] = useState<StreamFrame[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
  const sessionRef = useRef<string | null>(null)
  const goalRef = useRef<string | null>(null)

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
      wsRef.current = null
    }
    setStatus('idle')
  }, [])

  const connect = useCallback((sessionId: string, goal: string) => {
    sessionRef.current = sessionId
    goalRef.current = goal
    retriesRef.current = 0
    setFrames([])
    setStatus('connecting')

    const doConnect = () => {
      const token = getToken()
      if (!token) {
        setStatus('error')
        return
      }
      const wsBase = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${wsBase}//${window.location.host}/ws/run/${sessionId}?token=${encodeURIComponent(token)}`
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        // Send start frame with goal
        ws.send(JSON.stringify({ type: 'start', goal }))
      }

      ws.onmessage = (evt) => {
        try {
          const frame = JSON.parse(evt.data as string) as StreamFrame
          setFrames((prev) => [...prev, frame])
          if (frame.type === 'connected') {
            setStatus('connected')
            retriesRef.current = 0
          }
          if (frame.type === 'done' || frame.type === 'error') {
            setStatus('done')
          }
        } catch {
          // malformed frame — ignore
        }
      }

      ws.onerror = () => {
        setStatus('error')
      }

      ws.onclose = () => {
        if (retriesRef.current < MAX_RETRIES) {
          retriesRef.current++
          const delay = BASE_DELAY_MS * 2 ** (retriesRef.current - 1)
          setStatus('connecting')
          setTimeout(doConnect, delay)
        } else {
          setStatus('error')
        }
      }
    }

    doConnect()
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [])

  return { frames, status, connect, disconnect }
}
