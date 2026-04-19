import { useContext } from 'react'
import { Link } from 'react-router-dom'
import { SessionRunningContext } from '../context/SessionRunningContext'
import type { ProviderModeResponse } from '../lib/types'
import ProviderToggle from './ProviderToggle'

interface Props {
  onModeChange?: (resp: ProviderModeResponse) => void
}

export default function Navbar({ onModeChange }: Props) {
  const { isRunning } = useContext(SessionRunningContext)

  return (
    <nav className="flex items-center justify-between border-b border-gray-800 bg-gray-950 px-6 py-3">
      <Link to="/" className="flex items-center gap-2">
        <span className="text-lg font-bold text-indigo-400 tracking-tight">Nexus</span>
        <span className="hidden text-xs text-gray-500 sm:block">multi-agent platform</span>
      </Link>

      <ProviderToggle isSessionRunning={isRunning} onModeChange={onModeChange} />
    </nav>
  )
}
