import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { getToken } from './lib/api'
import Home from './pages/Home'
import Session from './pages/Session'

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getToken()) {
    // Simple redirect — a real app would show a login page
    return <Navigate to="/?auth=required" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  )
}
