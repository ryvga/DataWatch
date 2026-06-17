import { useCallback, useEffect, useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { AlertTriangle, Bell, CheckCircle2, ExternalLink, ShieldAlert, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getIncidents } from '../api/endpoints'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

const STORAGE_KEY = 'dw_dismissed_notifs'

function loadDismissed() {
  try { return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')) }
  catch { return new Set() }
}

function saveDismissed(set) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...set].slice(-200))) }
  catch {}
}

const SEV = {
  P1: { Icon: ShieldAlert, color: 'text-red-500', bg: 'bg-red-500/10', label: 'Critical' },
  P2: { Icon: AlertTriangle, color: 'text-orange-500', bg: 'bg-orange-500/10', label: 'Warning' },
  P3: { Icon: AlertTriangle, color: 'text-yellow-500', bg: 'bg-yellow-500/10', label: 'Info' },
}

export default function NotificationPanel({ collapsed = false }) {
  const [open, setOpen] = useState(false)
  const [incidents, setIncidents] = useState([])
  const [dismissed, setDismissed] = useState(loadDismissed)

  const load = useCallback(async () => {
    try {
      const res = await getIncidents({ status: 'open', limit: 20 })
      setIncidents(Array.isArray(res.data) ? res.data : [])
    } catch { /* silent - don't break sidebar on network error */ }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (open) load() }, [open, load])

  const visible = incidents.filter(i => !dismissed.has(i.id))

  // "New" = created in last 24h and not dismissed
  const newCount = visible.filter(i =>
    Date.now() - new Date(i.created_at).getTime() < 86_400_000
  ).length

  const dismiss = useCallback((id, e) => {
    e.preventDefault()
    e.stopPropagation()
    setDismissed(prev => {
      const next = new Set(prev)
      next.add(id)
      saveDismissed(next)
      return next
    })
  }, [])

  const clearAll = useCallback(() => {
    setDismissed(prev => {
      const next = new Set([...prev, ...incidents.map(i => i.id)])
      saveDismissed(next)
      return next
    })
  }, [incidents])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size={collapsed ? 'icon' : 'default'}
          title={collapsed ? 'Notifications' : undefined}
          aria-label="Notifications"
          className={cn(
            'relative w-full border border-transparent transition-colors',
            'hover:border-sidebar-border hover:bg-sidebar-accent',
            collapsed ? 'justify-center' : 'justify-start gap-2 px-2'
          )}
        >
          <Bell className="size-4 shrink-0 text-sidebar-foreground/65" />
          {!collapsed && (
            <span className="text-sm font-medium text-sidebar-foreground/65">Notifications</span>
          )}
          {newCount > 0 && (
            <span
              className={cn(
                'flex items-center justify-center rounded-full bg-red-500 font-bold text-white',
                collapsed
                  ? 'absolute right-1 top-1 size-4 text-[9px]'
                  : 'ml-auto size-5 shrink-0 text-[10px]'
              )}
            >
              {newCount > 9 ? '9+' : newCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>

      <PopoverContent
        side="right"
        align="end"
        sideOffset={12}
        className="w-[340px] shadow-2xl"
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Bell className="size-4 text-muted-foreground" />
            <span className="text-sm font-semibold">Notifications</span>
            {visible.length > 0 && (
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[11px] font-semibold tabular-nums">
                {visible.length}
              </span>
            )}
          </div>
          {visible.length > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={clearAll}
              className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
            >
              Clear all
            </Button>
          )}
        </div>

        <ScrollArea className="max-h-[380px]">
          {visible.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
              <div className="flex size-11 items-center justify-center rounded-full bg-emerald-500/10">
                <CheckCircle2 className="size-5 text-emerald-500" />
              </div>
              <p className="text-sm font-semibold">All caught up</p>
              <p className="text-xs text-muted-foreground">No open incidents right now</p>
            </div>
          ) : (
            <div className="divide-y">
              {visible.map(incident => {
                const s = SEV[incident.severity] ?? SEV.P3
                const Icon = s.Icon
                const isNew = Date.now() - new Date(incident.created_at).getTime() < 86_400_000
                return (
                  <Link
                    key={incident.id}
                    to={`/incidents/${incident.id}`}
                    onClick={() => setOpen(false)}
                    className="group relative flex items-start gap-3 px-4 py-3 transition-colors hover:bg-muted/50"
                  >
                    {isNew && (
                      <span className="absolute left-1.5 top-4 size-1.5 rounded-full bg-primary" />
                    )}

                    <div className={cn('mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg', s.bg)}>
                      <Icon className={cn('size-4', s.color)} />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className={cn('text-[11px] font-bold tracking-wide', s.color)}>
                          {incident.severity}
                        </span>
                        <span className="text-[11px] text-muted-foreground">
                          · {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
                        </span>
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-xs font-medium leading-snug text-foreground">
                        {incident.title}
                      </p>
                      <p className="mt-0.5 text-[11px] capitalize text-muted-foreground">
                        {incident.status}
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={e => dismiss(incident.id, e)}
                      aria-label="Dismiss notification"
                      className={cn(
                        'mt-0.5 flex size-6 shrink-0 items-center justify-center rounded',
                        'text-muted-foreground transition-all',
                        'opacity-0 group-hover:opacity-100',
                        'hover:bg-muted hover:text-foreground'
                      )}
                    >
                      <X className="size-3.5" />
                    </button>
                  </Link>
                )
              })}
            </div>
          )}
        </ScrollArea>

        <div className="border-t px-4 py-2.5">
          <Link
            to="/incidents"
            onClick={() => setOpen(false)}
            className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            View all incidents
            <ExternalLink className="size-3" />
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  )
}
