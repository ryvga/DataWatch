import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const SEVERITY_STYLES = {
  P1: 'border-red-700/30 bg-red-700/10 text-red-800 dark:text-red-300',
  P2: 'border-orange-700/30 bg-orange-600/10 text-orange-800 dark:text-orange-300',
  P3: 'border-amber-700/30 bg-amber-500/12 text-amber-800 dark:text-amber-300',
}

export default function SeverityBadge({ severity, className }) {
  const value = String(severity || 'P?').toUpperCase()

  return (
    <Badge
      variant="outline"
      className={cn('font-semibold tabular-nums', SEVERITY_STYLES[value] || 'text-muted-foreground', className)}
    >
      {value}
    </Badge>
  )
}
