import { Badge } from '@/components/ui/badge'

export const PAGE_SIZE = 50

export const PLANS = ['free', 'starter', 'growth', 'agency']
export const PLAN_PRICES = {
  free: 0,
  starter: 49,
  growth: 149,
  agency: 299,
  enterprise: 299,
}

export const SUBSCRIPTION_STATUSES = [
  'trialing',
  'approval_pending',
  'active',
  'past_due',
  'canceled',
  'cancelled',
  'suspended',
]

export const USER_ROLES = ['owner', 'admin', 'member', 'viewer']

export function unwrapList(data) {
  if (Array.isArray(data)) return { items: data, total: data.length }
  const items = data?.items || data?.results || data?.data || []
  return { items: Array.isArray(items) ? items : [], total: data?.total ?? items.length ?? 0 }
}

export function formatDate(value, fallback = '-') {
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return fallback
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatDateTime(value, fallback = '-') {
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return fallback
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatMoney(value) {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value || 0)
}

export function compactNumber(value) {
  return new Intl.NumberFormat(undefined, { notation: value >= 10000 ? 'compact' : 'standard' }).format(value || 0)
}

export function getOrgMembersCount(org) {
  return org?.members_count ?? org?.member_count ?? org?.user_count ?? org?.users_count ?? 0
}

export function getOrgTablesCount(org) {
  return org?.tables_count ?? org?.table_count ?? org?.monitored_tables_count ?? 0
}

export function getOrgSourcesCount(org) {
  return org?.sources_count ?? org?.source_count ?? org?.data_sources_count ?? 0
}

export function isActiveSubscription(status) {
  return ['active', 'trialing'].includes(String(status || '').toLowerCase())
}

export function estimateMrr(orgs) {
  return orgs.reduce((sum, org) => {
    if (!isActiveSubscription(org.subscription_status)) return sum
    return sum + (PLAN_PRICES[String(org.plan || 'free').toLowerCase()] || 0)
  }, 0)
}

export function planDetails(plan) {
  const monthly = PLAN_PRICES[String(plan || 'free').toLowerCase()] || 0
  if (!monthly) return 'Free plan, no monthly subscription'
  return `${formatMoney(monthly)} / month estimate`
}

export function PlanBadge({ plan }) {
  const value = String(plan || 'free')
  const variant = value === 'free' ? 'secondary' : value === 'agency' || value === 'enterprise' ? 'default' : 'outline'
  return <Badge variant={variant} className="capitalize">{value}</Badge>
}

export function StatusBadge({ status }) {
  const value = String(status || 'unknown')
  const destructive = ['past_due', 'canceled', 'cancelled', 'suspended', 'inactive'].includes(value)
  const active = ['active', 'trialing'].includes(value)
  return (
    <Badge variant={destructive ? 'destructive' : active ? 'default' : 'outline'} className="capitalize">
      {value.replaceAll('_', ' ')}
    </Badge>
  )
}

export function BooleanBadge({ value, trueLabel = 'Yes', falseLabel = 'No' }) {
  return (
    <Badge variant={value ? 'outline' : 'secondary'} className={value ? 'border-emerald-500/40 text-emerald-700 dark:text-emerald-300' : ''}>
      {value ? trueLabel : falseLabel}
    </Badge>
  )
}

export function getUserActive(user) {
  return user?.is_active ?? user?.active ?? user?.status !== 'inactive'
}

export function clientFilterOrgs(orgs, { search = '', plan = 'all', status = 'all' }) {
  const q = search.trim().toLowerCase()
  return orgs.filter((org) => {
    const matchesSearch = !q || [org.name, org.slug].some((value) => String(value || '').toLowerCase().includes(q))
    const matchesPlan = plan === 'all' || org.plan === plan
    const matchesStatus = status === 'all' || org.subscription_status === status
    return matchesSearch && matchesPlan && matchesStatus
  })
}

export function clientFilterUsers(users, { search = '', org = 'all', role = 'all', active = 'all' }) {
  const q = search.trim().toLowerCase()
  return users.filter((user) => {
    const matchesSearch = !q || [user.email, user.full_name].some((value) => String(value || '').toLowerCase().includes(q))
    const matchesOrg = org === 'all' || user.org_slug === org || user.org_id === org
    const matchesRole = role === 'all' || user.role === role
    const isActive = getUserActive(user)
    const matchesActive = active === 'all' || (active === 'active' ? isActive : !isActive)
    return matchesSearch && matchesOrg && matchesRole && matchesActive
  })
}
