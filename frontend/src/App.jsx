import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { isSessionValid, storage } from './lib/storage'
import { getHostContext, DEV_MODE } from './lib/subdomain'
import Layout from './components/Layout'
import Login from './pages/Login'
import Landing from './pages/Landing'
import Overview from './pages/Overview'
import Tables from './pages/Tables'
import Monitors from './pages/Monitors'
import Incidents from './pages/Incidents'
import IncidentDetail from './pages/IncidentDetail'
import TableDetail from './pages/TableDetail'
import Settings from './pages/Settings'
import Reports from './pages/Reports'
import AdminLogin from './pages/admin/AdminLogin'
import AdminLayout from './pages/admin/AdminLayout'
import AdminOrgs from './pages/admin/AdminOrgs'
import AdminOrgDetail from './pages/admin/AdminOrgDetail'
import AdminUsers from './pages/admin/AdminUsers'
import AdminStaff from './pages/admin/AdminStaff'

function ProtectedRoute({ children }) {
  if (!isSessionValid()) return <Navigate to="/login" replace />
  return children
}

function AdminRoute({ children }) {
  if (!storage.getItem('dw_staff_token')) return <Navigate to="/login" replace />
  return children
}

// Dev-only context label (bottom-right, tiny, no navigation links that expose admin path)
function DevBadge({ ctx }) {
  if (!DEV_MODE) return null
  return (
    <div style={{
      position: 'fixed', bottom: 8, right: 8, zIndex: 9999,
      background: 'hsl(220 13% 14%)', border: '1px solid hsl(220 13% 25%)',
      borderRadius: 5, padding: '3px 8px', fontSize: 10, fontFamily: 'monospace',
      color: '#64748b', pointerEvents: 'none'
    }}>
      ctx: <span style={{ color: '#38bdf8' }}>{ctx.type}</span>
      {ctx.workspace && <span style={{ color: '#a78bfa' }}> [{ctx.workspace}]</span>}
    </div>
  )
}

export default function App() {
  const ctx = getHostContext()

  if (ctx.type === 'admin') {
    return (
      <>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<AdminLogin />} />
            <Route path="/" element={<AdminRoute><AdminLayout /></AdminRoute>}>
              <Route index element={<Navigate to="/orgs" replace />} />
              <Route path="orgs" element={<AdminOrgs />} />
              <Route path="orgs/:id" element={<AdminOrgDetail />} />
              <Route path="users" element={<AdminUsers />} />
              <Route path="staff" element={<AdminStaff />} />
            </Route>
            <Route path="*" element={<Navigate to="/orgs" replace />} />
          </Routes>
        </BrowserRouter>
        <DevBadge ctx={ctx} />
      </>
    )
  }

  if (ctx.type === 'workspace') {
    return (
      <>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
              <Route index element={<Overview />} />
              <Route path="tables" element={<Tables />} />
              <Route path="tables/:id" element={<TableDetail />} />
              <Route path="monitors" element={<Monitors />} />
              <Route path="incidents" element={<Incidents />} />
              <Route path="incidents/:id" element={<IncidentDetail />} />
              <Route path="reports" element={<Reports />} />
              <Route path="settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <DevBadge ctx={ctx} />
      </>
    )
  }

  // Landing (default: localhost, main domain)
  return (
    <>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <DevBadge ctx={ctx} />
    </>
  )
}
