import { useState, type FormEvent } from 'react'

interface Props {
  onSubmit: (goal: string) => void
  isLoading: boolean
}

export default function GoalInput({ onSubmit, isLoading }: Props) {
  const [goal, setGoal] = useState('')
  const remaining = 4000 - goal.length

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (goal.trim().length > 0 && !isLoading) onSubmit(goal.trim())
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <textarea
        className="w-full rounded-xl border border-gray-700 bg-gray-900 p-4 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
        rows={4}
        maxLength={4000}
        placeholder="Describe your goal — e.g. 'Research the latest advances in protein folding and summarise them'"
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        disabled={isLoading}
      />
      <div className="flex items-center justify-between">
        <span className={`text-xs ${remaining < 100 ? 'text-amber-400' : 'text-gray-500'}`}>
          {remaining} chars remaining
        </span>
        <button
          type="submit"
          disabled={isLoading || goal.trim().length === 0}
          className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isLoading ? 'Starting…' : 'Run Nexus'}
        </button>
      </div>
    </form>
  )
}
