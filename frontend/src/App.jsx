import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import Activity from './pages/Activity'
import Bills from './pages/Bills'
import Dashboard from './pages/Dashboard'
import Import from './pages/Import'
import Insights from './pages/Insights'
import Login from './pages/Login'
import More from './pages/More'
import Planner from './pages/Planner'
import Settings from './pages/Settings'
import Subscriptions from './pages/Subscriptions'
import { useApp } from './state'

export default function App() {
  const { session } = useApp()

  if (session === undefined) {
    return <div className="boot"><Spinner /></div>
  }
  if (session === null) {
    return <Login />
  }
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="activity" element={<Activity />} />
        <Route path="bills" element={<Bills />} />
        <Route path="insights" element={<Insights />} />
        <Route path="planner" element={<Planner />} />
        <Route path="budgets" element={<Navigate to="/planner" replace />} />
        <Route path="subscriptions" element={<Subscriptions />} />
        <Route path="import" element={<Import />} />
        <Route path="settings" element={<Settings />} />
        <Route path="more" element={<More />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
