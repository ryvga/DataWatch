import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const INTERVALS = [
  { label: '10s', ms: 10000 },
  { label: '30s', ms: 30000 },
  { label: '1 min', ms: 60000 },
  { label: '5 min', ms: 300000 },
  { label: 'Off', ms: 0 },
]

function timeAgoLabel(lastRefreshed) {
  if (!lastRefreshed) return null
  const diffMs = Date.now() - lastRefreshed.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 5) return 'just now'
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin} min ago`
  return `${Math.floor(diffMin / 60)}h ago`
}

/**
 * RefreshBar — compact polling toolbar element
 *
 * Props:
 *   isRefreshing    boolean
 *   lastRefreshed   Date | null
 *   onRefresh       () => void
 *   interval        number (ms)
 *   onIntervalChange (ms: number) => void
 */
export default function RefreshBar({ isRefreshing, lastRefreshed, onRefresh, interval, onIntervalChange }) {
  const [, tick] = useState(0)

  // Re-render every second so the "X ago" label stays fresh
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const label = timeAgoLabel(lastRefreshed)
  const currentInterval = INTERVALS.find((i) => i.ms === interval) ? String(interval) : String(INTERVALS[1].ms)

  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <button
        type="button"
        onClick={onRefresh}
        disabled={isRefreshing}
        aria-label="Refresh now"
        className={cn(
          'flex items-center justify-center rounded-md p-1 transition-colors',
          'hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-50'
        )}
      >
        <RefreshCw className={cn('size-3.5', isRefreshing && 'animate-spin')} />
      </button>

      {label && (
        <span className="hidden sm:inline whitespace-nowrap">
          {isRefreshing ? 'Refreshing…' : `Updated ${label}`}
        </span>
      )}

      <Select
        value={currentInterval}
        onValueChange={(v) => onIntervalChange(Number(v))}
      >
        <SelectTrigger className="h-6 w-[4.5rem] border-none bg-transparent px-1.5 text-xs shadow-none focus:ring-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent align="end">
          <SelectGroup>
            {INTERVALS.map((item) => (
              <SelectItem key={item.ms} value={String(item.ms)} className="text-xs">
                {item.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </div>
  )
}
