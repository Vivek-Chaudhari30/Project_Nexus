const AGENTS = ['planner', 'researcher', 'executor', 'verifier', 'reflector'] as const

interface Props {
  activeAgent: string | null
  completedAgents: Set<string>
  iteration: number
}

function pill(agent: string, active: boolean, done: boolean) {
  let cls = 'rounded-full px-3 py-1 text-xs font-semibold transition-all duration-300 '
  if (active)  cls += 'bg-indigo-500 text-white ring-2 ring-indigo-300 scale-110'
  else if (done) cls += 'bg-green-700 text-green-100'
  else           cls += 'bg-gray-800 text-gray-400'
  return <span key={agent} className={cls}>{agent}</span>
}

export default function PipelineVisualizer({ activeAgent, completedAgents, iteration }: Props) {
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Pipeline</span>
        {iteration > 0 && (
          <span className="text-xs text-indigo-400">Iteration {iteration}</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {AGENTS.map((a, i) => (
          <>
            {pill(a, activeAgent === a, completedAgents.has(a))}
            {i < AGENTS.length - 1 && (
              <span className="text-gray-600 text-xs">→</span>
            )}
          </>
        ))}
      </div>
    </div>
  )
}
