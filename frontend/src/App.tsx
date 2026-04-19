import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Navbar from './components/Navbar'
import { SessionRunningContext } from './context/SessionRunningContext'
import { getToken } from './lib/api'
import Home from './pages/Home'
import Session from './pages/Session'

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getToken()) {
    return <Navigate to="/?auth=required" replace />
  }
  return <>{children}</>
}

export default function App() {
  const [isRunning, setRunning] = useState(false)

  return (
    <SessionRunningContext.Provider value={{ isRunning, setRunning }}>
      <BrowserRouter>
        <div className="flex min-h-screen flex-col bg-gray-950">
          <Navbar />
          <div className="flex-1">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route
                path="/session/:sessionId"
                element={
                  <RequireAuth>
                    <Session />
                  </RequireAuth>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </SessionRunningContext.Provider>
  )
}
