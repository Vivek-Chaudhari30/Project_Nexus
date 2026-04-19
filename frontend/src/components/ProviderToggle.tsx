import { useCallback, useEffect, useRef, useState } from 'react'
import { getProviderMode, setProviderMode } from '../lib/api'
import type { ProviderMode, ProviderModeResponse } from '../lib/types'

interface Props {
  isSessionRunning: boolean
  onModeChange?: (resp: ProviderModeResponse) => void
}

export default function ProviderToggle({ isSessionRunning, onModeChange }: Props) {
  const [current, setCurrent] = useState<ProviderModeResponse | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [switching, setSwitching] = useState(false)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    getProviderMode().then(setCurrent).catch(() => null)
  }, [])

  const showToast = useCallback((msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast(msg)
    toastTimer.current = setTimeout(() => setToast(null), 3000)
  }, [])

  const handleSwitch = useCallback(
    async (mode: ProviderMode) => {
      if (isSessionRunning || switching || current?.mode === mode) return
      setSwitching(true)
      try {
        const resp = await setProviderMode(mode)
        setCurrent(resp)
        onModeChange?.(resp)
        showToast(
          mode === 'openai_only' ? 'Switched to OpenAI Only' : 'Switched to Multi-Provider'
        )
      } catch {
        showToast('Failed to switch provider mode')
      } finally {
        setSwitching(false)
      }
    },
    [isSessionRunning, switching, current, onModeChange, showToast]
  )

  const disabled = isSessionRunning || switching

  return (
    <div className="relative flex flex-col items-end gap-1">
      {/* Pill toggle */}
      <div
        className={`flex rounded-full border p-0.5 transition-opacity ${
          disabled
            ? 'border-gray-700 opacity-40 cursor-not-allowed'
            : 'border-gray-600 cursor-pointer'
        }`}
        title={isSessionRunning ? 'Cannot switch provider while a session is running' : undefined}
      >
        {/* Multi-Provider option */}
        <button
          disabled={disabled}
          onClick={() => handleSwitch('multi')}
          className={`flex flex-col items-center rounded-full px-3 py-1 text-xs font-semibold transition-all ${
            current?.mode === 'multi'
              ? 'bg-indigo-600 text-white'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <span>Multi-Provider</span>
          <span className="text-[10px] font-normal opacity-70 mt-0.5">
            Anthropic · OpenAI · Google
          </span>
        </button>

        {/* OpenAI Only option */}
        <button
          disabled={disabled}
          onClick={() => handleSwitch('openai_only')}
          className={`flex flex-col items-center rounded-full px-3 py-1 text-xs font-semibold transition-all ${
            current?.mode === 'openai_only' || current === null
              ? 'bg-indigo-600 text-white'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <span>OpenAI Only</span>
          <span className="text-[10px] font-normal opacity-70 mt-0.5">OpenAI · All Models</span>
        </button>
      </div>

      {/* Toast */}
      {toast && (
        <div className="absolute top-full mt-2 right-0 z-50 rounded-lg bg-gray-800 border border-gray-600 px-3 py-1.5 text-xs text-gray-200 whitespace-nowrap shadow-lg animate-fade-in">
          {toast}
        </div>
      )}
    </div>
  )
}
