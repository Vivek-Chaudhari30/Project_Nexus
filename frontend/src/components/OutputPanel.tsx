interface Props {
  output: Record<string, string> | null
  disclaimer: string | null
}

export default function OutputPanel({ output, disclaimer }: Props) {
  if (!output || Object.keys(output).length === 0) return null

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Output</span>
        {disclaimer && (
          <span className="rounded bg-amber-900/50 px-2 py-0.5 text-xs text-amber-300">
            {disclaimer.replace(/_/g, ' ')}
          </span>
        )}
      </div>
      {Object.entries(output).map(([taskId, text]) => (
        <div key={taskId} className="space-y-1">
          <p className="text-xs text-gray-500 font-mono">{taskId}</p>
          <pre className="whitespace-pre-wrap text-sm text-gray-200 font-mono leading-relaxed overflow-x-auto">
            {text}
          </pre>
        </div>
      ))}
    </div>
  )
}
