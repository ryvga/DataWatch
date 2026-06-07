import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import clsx from 'clsx'

const links = [
  { to: '/', label: 'Overview', icon: '🏠', end: true },
  { to: '/tables', label: 'Tables', icon: '🗄️' },
  { to: '/incidents', label: 'Incidents', icon: '🚨' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function Layout() {
  const nav = useNavigate()

  const logout = () => {
    localStorage.removeItem('dw_token')
    localStorage.removeItem('dw_api_key')
    nav('/login')
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="px-5 py-5 border-b border-gray-800">
          <span className="text-lg font-bold text-white tracking-tight">🔭 DataWatch</span>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-blue-600/20 text-blue-400'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                )
              }
            >
              <span>{l.icon}</span>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-gray-800 space-y-1">
          <button
            onClick={() => nav('/incidents?assigned_to_me=true')}
            title="View incidents assigned to me"
            aria-label="My incidents"
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-500 hover:bg-gray-800 hover:text-gray-300 transition-colors"
          >
            <span>🔔</span> My Incidents
          </button>
          <button
            onClick={logout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-500 hover:bg-gray-800 hover:text-gray-300 transition-colors"
          >
            <span>🚪</span> Sign Out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
