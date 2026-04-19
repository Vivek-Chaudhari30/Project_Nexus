import { useEffect, useMemo } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import OutputPanel from '../components/OutputPanel'
import PipelineVisualizer from '../components/PipelineVisualizer'
import QualityMeter from '../components/QualityMeter'
import SessionSidebar from '../components/SessionSidebar'
import StreamLog from '../components/StreamLog'
import { useNexusStream } from '../hooks/useNexusStream'
import type { DoneFrame, QualityScoreFrame } from '../lib/types'

export default function Session() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const goal = (location.state as { goal?: string } | null)?.goal ?? ''

  const { frames, status, connect, disconnect } = useNexusStream()

  useEffect(() => {
    if (sessionId && goal) {
      connect(sessionId, goal)
    }
    return () => disconnect()
  }, [sessionId, goal, connect, disconnect])

  const activeAgent = useMemo(() => {
    for (let i = frames.length - 1; i >= 0; i--) {
      const f = frames[i]
      if (f.type === 'agent_start') return f.agent
      if (f.type === 'agent_complete') return null
    }
    return null
  }, [frames])

  const completedAgents = useMemo(() => {
    const done = new Set<string>()
    for (const f of frames) {
      if (f.type === 'agent_complete') done.add(f.agent)
    }
    return done
  }, [frames])

  const currentIteration = useMemo(() => {
    for (let i = frames.length - 1; i >= 0; i--) {
      const f = frames[i]
      if (f.type === 'agent_start') return f.iteration
    }
    return 0
  }, [frames])

  const latestQuality = useMemo<QualityScoreFrame | null>(() => {
    for (let i = frames.length - 1; i >= 0; i--) {
      const f = frames[i]
      if (f.type === 'quality_score') return f
    }
    return null
  }, [frames])

  const doneFrame = useMemo<DoneFrame | null>(() => {
    for (const f of frames) {
      if (f.type === 'done') return f
    }
    return null
  }, [frames])

  return (
    <div className="flex h-full bg-gray-950 text-gray-100">
      <SessionSidebar />
      <main className="flex-1 overflow-y-auto p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <button
              onClick={() => navigate('/')}
              className="text-xs text-gray-500 hover:text-gray-300 mb-1"
            >
              ← Back
            </button>
            <h2 className="text-lg font-semibold text-white truncate max-w-lg">{goal || 'Session'}</h2>
          </div>
          <span
            className={`text-xs rounded-full px-3 py-1 font-medium ${
              status === 'connected' ? 'bg-indigo-900 text-indigo-300' :
              status === 'done'      ? 'bg-emerald-900 text-emerald-300' :
              status === 'error'     ? 'bg-red-900 text-red-300' :
                                       'bg-gray-800 text-gray-400'
            }`}
          >
            {status}
          </span>
        </div>

        <PipelineVisualizer
          activeAgent={activeAgent}
          completedAgents={completedAgents}
          iteration={currentIteration}
        />

        <StreamLog frames={frames} />

        {latestQuality && (
          <QualityMeter
            score={latestQuality.score}
            breakdown={latestQuality.breakdown}
          />
        )}

        {doneFrame && (
          <OutputPanel
            output={doneFrame.output}
            disclaimer={doneFrame.disclaimer}
          />
        )}
      </main>
    </div>
  )
}
