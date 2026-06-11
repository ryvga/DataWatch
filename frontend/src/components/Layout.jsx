import { NavLink, Outlet, useNavigate, Link } from 'react-router-dom'
import { useState } from 'react'
import {
  AlertTriangle,
  BarChart3,
  Bell,
  BookOpen,
  Building2,
  ChevronUp,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sun,
  Table2,
  UserCircle,
  Users,
} from 'lucide-react'
import { useTheme } from 'next-themes'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { BrandMark } from './app-ui'
import { cn } from '@/lib/utils'
import { clearSession, storage } from '@/lib/storage'

const links = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/tables', label: 'Tables', icon: Table2 },
  { to: '/teams', label: 'Teams', icon: Users },
  { to: '/incidents', label: 'Incidents', icon: AlertTriangle },
  { to: '/reports', label: 'Reports', icon: BarChart3 },
  { to: '/help', label: 'Help Center', icon: BookOpen },
  { to: '/settings', label: 'Settings', icon: Settings },
]

function NavItems({ onNavigate, collapsed = false }) {
  return (
    <nav className="flex flex-col gap-0.5">
      {links.map((link) => {
        const Icon = link.icon
        return (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            onClick={onNavigate}
            title={collapsed ? link.label : undefined}
            aria-label={collapsed ? link.label : undefined}
            className={({ isActive }) =>
              cn(
                'flex h-9 items-center gap-2.5 rounded-lg text-sm font-medium transition-all duration-150',
                'dw-nav-link group/nav',
                collapsed ? 'w-10 justify-center px-0' : 'px-3',
                isActive
                  ? 'bg-primary/12 text-primary border border-primary/25 shadow-sm font-semibold'
                  : 'text-sidebar-foreground/65 hover:bg-sidebar-accent hover:text-sidebar-foreground border border-transparent font-medium'
              )
            }
          >
            <Icon className="size-4 shrink-0" />
            {!collapsed && <span>{link.label}</span>}
          </NavLink>
        )
      })}
    </nav>
  )
}

export default function Layout() {
  const nav = useNavigate()
  const { resolvedTheme, setTheme } = useTheme()
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('dw_sidebar_collapsed') === '1' } catch { return false }
  })

  const orgName = storage.getItem('dw_org_name') || 'Workspace'
  const userEmail = storage.getItem('dw_user_email') || ''
  const userName = storage.getItem('dw_user_name') || userEmail.split('@')[0] || 'You'
  const userRole = storage.getItem('dw_user_role') || 'member'

  const logout = () => {
    clearSession()
    nav('/login')
  }

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev
      try { localStorage.setItem('dw_sidebar_collapsed', next ? '1' : '0') } catch {}
      return next
    })
  }

  const renderWorkspaceMenu = (compact = false) => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size={compact ? 'icon' : 'default'}
          className={cn(
            'w-full border border-transparent hover:border-sidebar-border hover:bg-sidebar-accent',
            compact ? 'justify-center' : 'justify-start gap-2 px-2'
          )}
          aria-label="Workspace menu"
        >
          <div className={cn('flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary text-xs font-bold', compact && 'size-8')}>
            {orgName.charAt(0).toUpperCase()}
          </div>
          {!compact && (
            <div className="flex min-w-0 flex-1 flex-col items-start">
              <span className="truncate text-xs font-semibold text-sidebar-foreground leading-tight max-w-[140px]">{orgName}</span>
              <span className="truncate text-[10px] text-sidebar-foreground/50 leading-tight max-w-[140px]">{userName} · {userRole}</span>
            </div>
          )}
          {!compact && <ChevronUp className="ml-auto size-3.5 text-sidebar-foreground/40" />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        side={compact ? 'right' : 'top'}
        className="w-60 bg-popover"
        sideOffset={8}
      >
        <div className="px-3 py-2 border-b">
          <p className="text-xs font-semibold truncate">{userName}</p>
          <p className="text-[11px] text-muted-foreground truncate">{userEmail}</p>
          <div className="mt-1 flex items-center gap-1.5">
            <Building2 className="size-3 text-muted-foreground" />
            <span className="text-[11px] text-muted-foreground">{orgName}</span>
            <span className="ml-auto rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium capitalize">{userRole}</span>
          </div>
        </div>
        <DropdownMenuLabel className="text-xs text-muted-foreground font-normal mt-1">Appearance</DropdownMenuLabel>
        <DropdownMenuGroup>
          <DropdownMenuItem
            onClick={() => setTheme('light')}
            className={cn(resolvedTheme === 'light' && 'bg-muted text-foreground')}
          >
            <Sun className="size-4 mr-2" />
            Light mode
            {resolvedTheme === 'light' && <span className="ml-auto text-xs text-muted-foreground">Active</span>}
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => setTheme('dark')}
            className={cn(resolvedTheme === 'dark' && 'bg-muted text-foreground')}
          >
            <Moon className="size-4 mr-2" />
            Dark mode
            {resolvedTheme === 'dark' && <span className="ml-auto text-xs text-muted-foreground">Active</span>}
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/settings?tab=profile">
            <UserCircle className="size-4 mr-2" />
            Profile settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive focus:bg-destructive/10">
          <LogOut className="size-4 mr-2" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop sidebar */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 hidden flex-col border-r bg-sidebar transition-[width] duration-200 lg:flex',
          collapsed ? 'w-[60px]' : 'w-[240px]'
        )}
      >
        {/* Logo */}
        <div
          className={cn(
            'flex h-14 shrink-0 items-center border-b border-sidebar-border px-3',
            collapsed ? 'justify-center' : 'justify-between'
          )}
        >
          {collapsed ? (
            <BrandMark iconOnly />
          ) : (
            <>
              <BrandMark />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={toggleCollapsed}
                className="size-7 hover:bg-sidebar-accent text-sidebar-foreground/60 hover:text-sidebar-foreground"
                aria-label="Collapse navigation"
              >
                <PanelLeftClose className="size-4" />
              </Button>
            </>
          )}
        </div>

        {/* Nav */}
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto px-2 py-3">
          {collapsed && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={toggleCollapsed}
              className="mx-auto size-8 mb-2 hover:bg-sidebar-accent text-sidebar-foreground/60 hover:text-sidebar-foreground"
              aria-label="Expand navigation"
            >
              <PanelLeftOpen className="size-4" />
            </Button>
          )}
          <NavItems collapsed={collapsed} />
        </div>

        {/* Bottom workspace menu */}
        <div className="border-t border-sidebar-border px-2 py-3">
          {!collapsed && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start gap-2 mb-1 text-sidebar-foreground/65 hover:bg-sidebar-accent hover:text-sidebar-foreground"
              onClick={() => nav('/incidents?assigned_to_me=true')}
              title="My assigned incidents"
            >
              <Bell className="size-4" />
              My Incidents
            </Button>
          )}
          {renderWorkspaceMenu(collapsed)}
        </div>
      </aside>

      {/* Main content offset */}
      <div className={cn('flex flex-col transition-[padding] duration-200', collapsed ? 'lg:pl-[60px]' : 'lg:pl-[240px]')}>
        {/* Mobile header */}
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-background/90 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:hidden">
          <BrandMark />
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">{orgName}</span>
            <Sheet>
              <SheetTrigger asChild>
                <Button type="button" variant="ghost" size="icon" aria-label="Open navigation">
                  <Menu className="size-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-72 bg-sidebar p-0">
                <SheetHeader className="h-14 flex-row items-center border-b border-sidebar-border px-4">
                  <SheetTitle asChild>
                    <BrandMark />
                  </SheetTitle>
                </SheetHeader>
                <div className="flex flex-1 flex-col justify-between px-3 py-3">
                  <NavItems />
                </div>
                <div className="border-t border-sidebar-border px-3 py-3">
                  {renderWorkspaceMenu(false)}
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </header>

        <main className="flex-1 min-h-[calc(100vh-3.5rem)] lg:min-h-screen">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
