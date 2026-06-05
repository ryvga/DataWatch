import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import {
  AlertTriangle,
  Database,
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
import { clearSession } from '@/lib/storage'

const links = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/tables', label: 'Tables', icon: Table2 },
  { to: '/incidents', label: 'Incidents', icon: AlertTriangle },
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
            compact ? 'justify-center' : 'justify-start'
          )}
          aria-label="Workspace menu"
        >
          <UserCircle className="size-4 shrink-0" />
          {!compact && <span className="truncate text-sm">Workspace</span>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        side={compact ? 'right' : 'top'}
        className="w-56 bg-popover"
        sideOffset={8}
      >
        <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">Appearance</DropdownMenuLabel>
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
          {renderWorkspaceMenu(collapsed)}
        </div>
      </aside>

      {/* Main content offset */}
      <div className={cn('flex flex-col transition-[padding] duration-200', collapsed ? 'lg:pl-[60px]' : 'lg:pl-[240px]')}>
        {/* Mobile header */}
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-background/90 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:hidden">
          <BrandMark />
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
        </header>

        <main className="flex-1 min-h-[calc(100vh-3.5rem)] lg:min-h-screen">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
