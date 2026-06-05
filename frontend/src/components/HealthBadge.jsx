import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const STATUS_STYLES = {
  healthy: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  passed: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  passing: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  connected: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  resolved: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  warning: 'border-amber-600/25 bg-amber-500/12 text-amber-700 dark:text-amber-300',
  acknowledged: 'border-amber-600/25 bg-amber-500/12 text-amber-700 dark:text-amber-300',
  pending: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
  paused: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
  'never-profiled': 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
  error: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  failed: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  failing: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  open: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  incident: 'border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-300',
}

export default function HealthBadge({ status, size = 'sm', className }) {
  const value = status || 'unknown'
  const key = String(value).toLowerCase()
  const label = key.replace(/[-_]/g, ' ')

  return (
    <Badge
      variant="outline"
      className={cn(
        'capitalize',
        size === 'lg' && 'h-6 px-2.5 text-sm',
        STATUS_STYLES[key] || 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
        className
      )}
    >
      {label}
    </Badge>
  )
}
