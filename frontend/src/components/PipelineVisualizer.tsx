import type { ProviderModeResponse } from '../lib/types'

const AGENTS = ['planner', 'researcher', 'executor', 'verifier', 'reflector'] as const

// Maps each agent to the model assignment key from ProviderModeResponse
const AGENT_MODEL_KEY: Record<string, keyof ProviderModeResponse['models']> = {
  planner:    'reasoning',
  researcher: 'extraction',
  executor:   'code',
  verifier:   'reasoning',
  reflector:  'reasoning',
}

interface Props {
  activeAgent: string | null
  completedAgents: Set<string>
  iteration: number
  modelAssignments: ProviderModeResponse['models'] | null
}

function pill(agent: string, active: boolean, done: boolean, modelName: string | null) {
  let cls = 'flex flex-col items-center rounded-xl px-3 py-1.5 text-xs font-semibold transition-all duration-300 '
  if (active)  cls += 'bg-indigo-500 text-white ring-2 ring-indigo-300 scale-110'
  else if (done) cls += 'bg-green-700 text-green-100'
  else           cls += 'bg-gray-800 text-gray-400'

  return (
    <div key={agent} className="flex flex-col items-center gap-0.5">
      <span className={cls}>{agent}</span>
      {modelName && (
        <span className="text-[10px] text-gray-500 font-mono truncate max-w-[80px]" title={modelName}>
          {modelName}
        </span>
      )}
    </div>
  )
}

export default function PipelineVisualizer({ activeAgent, completedAgents, iteration, modelAssignments }: Props) {
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Pipeline</span>
        {iteration > 0 && (
          <span className="text-xs text-indigo-400">Iteration {iteration}</span>
        )}
      </div>
      <div className="flex flex-wrap items-start gap-2">
        {AGENTS.map((a, i) => {
          const modelKey = AGENT_MODEL_KEY[a]
          const modelName = modelAssignments ? modelAssignments[modelKey] : null
          return (
            <div key={a} className="flex items-center gap-2">
              {pill(a, activeAgent === a, completedAgents.has(a), modelName)}
              {i < AGENTS.length - 1 && (
                <span className="text-gray-600 text-xs mt-1">→</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
