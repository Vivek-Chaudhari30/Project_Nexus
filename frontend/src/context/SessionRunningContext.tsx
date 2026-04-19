import { createContext } from 'react'

interface SessionRunningContextValue {
  isRunning: boolean
  setRunning: (running: boolean) => void
}

export const SessionRunningContext = createContext<SessionRunningContextValue>({
  isRunning: false,
  setRunning: () => undefined,
})
