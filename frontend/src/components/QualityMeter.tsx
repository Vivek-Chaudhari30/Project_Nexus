interface Props {
  score: number | null
  breakdown: Record<string, number>
}

function barColor(score: number): string {
  if (score >= 0.85) return 'bg-emerald-500'
  if (score >= 0.70) return 'bg-amber-400'
  return 'bg-red-500'
}

export default function QualityMeter({ score, breakdown }: Props) {
  if (score === null) return null

  const pct = Math.round(score * 100)
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Quality</span>
        <span className={`text-lg font-bold ${score >= 0.85 ? 'text-emerald-400' : score >= 0.70 ? 'text-amber-400' : 'text-red-400'}`}>
          {pct}%
        </span>
      </div>
      <div className="h-2 rounded-full bg-gray-700">
        <div
          className={`h-2 rounded-full transition-all duration-700 ${barColor(score)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {Object.keys(breakdown).length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {Object.entries(breakdown).map(([dim, val]) => (
            <div key={dim} className="text-center">
              <div className="text-xs text-gray-500 capitalize truncate">{dim.replace('_', ' ')}</div>
              <div className="text-sm font-semibold text-gray-200">{Math.round(val * 100)}%</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
