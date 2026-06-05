import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { isSessionValid } from './lib/storage'
import { getHostContext } from './lib/subdomain'
import Layout from './components/Layout'
import Login from './pages/Login'
import Landing from './pages/Landing'
import Overview from './pages/Overview'
import Tables from './pages/Tables'
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
import { storage } from './lib/storage'

function ProtectedRoute({ children }) {
  if (!isSessionValid()) return <Navigate to="/login" replace />
  return children
}

function AdminRoute({ children }) {
  if (!storage.getItem('dw_staff_token')) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const ctx = getHostContext()

  // Admin portal subdomain
  if (ctx.type === 'admin') {
    return (
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
    )
  }

  // Landing page (main domain or www)
  if (ctx.type === 'landing') {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    )
  }

  // Workspace app (subdomain or localhost dev)
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Overview />} />
          <Route path="tables" element={<Tables />} />
          <Route path="tables/:id" element={<TableDetail />} />
          <Route path="incidents" element={<Incidents />} />
          <Route path="incidents/:id" element={<IncidentDetail />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
