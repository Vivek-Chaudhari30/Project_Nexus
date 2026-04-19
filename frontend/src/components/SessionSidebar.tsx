import { Link } from 'react-router-dom'
import { useSessions } from '../hooks/useSessions'

function statusDot(status: string) {
  const colors: Record<string, string> = {
    pending:   'bg-gray-400',
    running:   'bg-indigo-400 animate-pulse',
    completed: 'bg-emerald-400',
    failed:    'bg-red-400',
    aborted:   'bg-gray-600',
  }
  return <span className={`inline-block h-2 w-2 rounded-full ${colors[status] ?? 'bg-gray-400'}`} />
}

export default function SessionSidebar() {
  const { sessions, isLoading } = useSessions()

  return (
    <aside className="w-64 flex-shrink-0 border-r border-gray-800 bg-gray-950 flex flex-col">
      <div className="p-4 border-b border-gray-800">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Sessions</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && <p className="p-4 text-xs text-gray-500">Loading…</p>}
        {sessions.map((s) => (
          <Link
            key={s.session_id}
            to={`/session/${s.session_id}`}
            className="flex items-start gap-2 p-3 hover:bg-gray-900 border-b border-gray-800/50 group"
          >
            <div className="mt-1">{statusDot(s.status)}</div>
            <div className="min-w-0">
              <p className="text-xs text-gray-200 truncate group-hover:text-white">{s.goal}</p>
              <p className="text-xs text-gray-600 mt-0.5">
                {s.final_quality != null ? `${Math.round(s.final_quality * 100)}%` : s.status}
              </p>
            </div>
          </Link>
        ))}
        {!isLoading && sessions.length === 0 && (
          <p className="p-4 text-xs text-gray-600">No sessions yet.</p>
        )}
      </div>
    </aside>
  )
}
