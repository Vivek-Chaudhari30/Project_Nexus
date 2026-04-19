import { useEffect, useRef } from 'react'
import type { StreamFrame } from '../lib/types'

interface Props {
  frames: StreamFrame[]
}

function frameColor(type: string): string {
  switch (type) {
    case 'agent_start':    return 'text-indigo-400'
    case 'agent_complete': return 'text-green-400'
    case 'quality_score':  return 'text-amber-400'
    case 'replan':         return 'text-orange-400'
    case 'error':          return 'text-red-400'
    case 'done':           return 'text-emerald-400'
    default:               return 'text-gray-400'
  }
}

function frameText(f: StreamFrame): string {
  switch (f.type) {
    case 'connected':      return `Connected to session ${f.session_id}`
    case 'agent_start':    return `[iter ${f.iteration}] ${f.agent} starting…`
    case 'agent_complete': return `${f.agent} done`
    case 'agent_progress': return `${f.agent}: ${f.message}`
    case 'quality_score':  return `Quality score: ${(f.score * 100).toFixed(1)}% (iter ${f.iteration})`
    case 'replan':         return `Replanning (iter ${f.iteration}): ${f.feedback}`
    case 'error':          return `Error [${f.code}]: ${f.message}`
    case 'done':           return `Done — final score ${(f.final_score * 100).toFixed(1)}%${f.disclaimer ? ` (${f.disclaimer})` : ''}`
    case 'pong':           return 'pong'
    default:               return JSON.stringify(f)
  }
}

export default function StreamLog({ frames }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [frames])

  return (
    <div className="h-48 overflow-y-auto rounded-xl border border-gray-700 bg-black p-3 font-mono text-xs">
      {frames.length === 0 && (
        <p className="text-gray-600">Awaiting stream…</p>
      )}
      {frames.map((f, i) => (
        <p key={i} className={`leading-5 ${frameColor(f.type)}`}>
          <span className="text-gray-600 mr-2">›</span>
          {frameText(f)}
        </p>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
