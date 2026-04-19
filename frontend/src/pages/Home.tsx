import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import GoalInput from '../components/GoalInput'
import SessionSidebar from '../components/SessionSidebar'
import * as api from '../lib/api'

export default function Home() {
  const navigate = useNavigate()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleGoalSubmit(goal: string) {
    setIsLoading(true)
    setError(null)
    try {
      const session = await api.createSession(goal)
      navigate(`/session/${session.session_id}`, { state: { goal } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex h-full bg-gray-950 text-gray-100">
      <SessionSidebar />
      <main className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-2xl space-y-6">
          <div className="space-y-2">
            <h1 className="text-3xl font-bold text-white tracking-tight">Project Nexus</h1>
            <p className="text-gray-400 text-sm">
              Multi-agent orchestration platform — 5 agents, quality-gated reflection loop.
            </p>
          </div>
          <GoalInput onSubmit={handleGoalSubmit} isLoading={isLoading} />
          {error && (
            <div className="rounded-lg bg-red-950 border border-red-800 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
