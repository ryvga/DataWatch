import { useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { BarChart3, Building2, LogOut, Users, UserCog } from 'lucide-react'
import { BrandMark, ThemeToggle } from '../../components/app-ui'
import { Button } from '@/components/ui/button'
import { storage } from '@/lib/storage'

function isStaffValid() {
  return !!storage.getItem('dw_staff_token')
}

const NAV = [
  { to: '/', icon: BarChart3, label: 'Dashboard', end: true },
  { to: '/orgs', icon: Building2, label: 'Organisations' },
  { to: '/users', icon: Users, label: 'All Users' },
  { to: '/staff', icon: UserCog, label: 'Staff' },
]

export default function AdminLayout() {
  const nav = useNavigate()

  useEffect(() => {
    if (!isStaffValid()) nav('/login', { replace: true })
  }, [])

  const logout = () => {
    storage.removeItem('dw_staff_token')
    storage.removeItem('dw_staff_email')
    nav('/login', { replace: true })
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
        <div className="flex items-center justify-between px-4 py-2.5">
          <div className="flex items-center gap-3">
            <BrandMark />
            <span className="rounded-full border border-orange-500/40 bg-orange-500/10 px-2 py-0.5 text-xs font-semibold text-orange-600 dark:text-orange-400">
              Admin
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-xs text-muted-foreground sm:block">
              {storage.getItem('dw_staff_email')}
            </span>
            <ThemeToggle />
            <Button variant="ghost" size="icon" onClick={logout} title="Sign out">
              <LogOut className="size-4" />
            </Button>
          </div>
        </div>
        <nav className="flex gap-0 border-t px-4">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`
              }
            >
              <item.icon className="size-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="flex-1 mx-auto w-full max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
