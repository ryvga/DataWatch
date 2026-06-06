import { AlertCircle, Database, Loader2, Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export function BrandMark({ className, iconOnly = false }) {
  return (
    <div className={cn('flex items-center gap-2.5', className)}>
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        {/* Eye icon — 100 eyes on your data, inspired by Panoptes */}
        <svg viewBox="0 0 32 32" aria-hidden="true" className="size-5">
          <ellipse cx="16" cy="16" rx="10" ry="7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
          <circle cx="16" cy="16" r="3.5" fill="currentColor" />
          <circle cx="16" cy="16" r="1.4" fill="none" stroke="white" strokeWidth="1" />
        </svg>
      </div>
      {!iconOnly && (
        <div className="min-w-0 leading-none">
          <div className="text-sm font-bold tracking-tight text-foreground">Panopta</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">100 eyes on your data</div>
        </div>
      )}
    </div>
  )
}

export function PageHeader({ title, description, actions, className }) {
  return (
    <div className={cn('flex flex-col gap-3 border-b pb-4 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label="Toggle theme"
    >
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}

export function LoadingState({ label = 'Loading data' }) {
  return (
    <div className="dw-page">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        {label}
      </div>
      <div className="grid gap-3">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    </div>
  )
}

export function ErrorNotice({ message, onDismiss }) {
  if (!message) return null
  const text = formatErrorMessage(message)

  return (
    <Alert variant="destructive">
      <AlertCircle className="size-4" />
      <AlertDescription className="flex items-center justify-between gap-3">
        <span>{text}</span>
        {onDismiss && (
          <Button type="button" size="xs" variant="ghost" onClick={onDismiss}>
            Dismiss
          </Button>
        )}
      </AlertDescription>
    </Alert>
  )
}

function formatErrorMessage(message) {
  if (typeof message === 'string') return message
  if (Array.isArray(message)) return message.map(formatErrorMessage).join('; ')
  if (message && typeof message === 'object') {
    if (message.msg) return String(message.msg)
    if (message.detail) return formatErrorMessage(message.detail)
    return Object.values(message).map(formatErrorMessage).filter(Boolean).join('; ') || 'Request failed'
  }
  return String(message)
}

export function EmptyState({ icon: Icon = Database, title, description, action }) {
  return (
    <Empty className="min-h-56 border bg-card">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Icon />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description && <EmptyDescription>{description}</EmptyDescription>}
      </EmptyHeader>
      {action && <EmptyContent>{action}</EmptyContent>}
    </Empty>
  )
}

export function formatDateTime(value) {
  if (!value) return 'Never'
  return new Date(value).toLocaleString()
}

export function formatNumber(value) {
  return value == null ? '—' : Number(value).toLocaleString()
}
