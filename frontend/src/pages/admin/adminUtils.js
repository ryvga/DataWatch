/** Shared utilities for the admin portal */

export const PAGE_SIZE = 50

export const PLANS = ['free', 'starter', 'growth', 'agency', 'enterprise']

export function BooleanBadge({ value, trueLabel = 'Yes', falseLabel = 'No' }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${value ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'border-stone-500/25 bg-stone-500/10 text-stone-600 dark:text-stone-400'}`}>
      {value ? trueLabel : falseLabel}
    </span>
  )
}

const PLAN_PRICES = {
  starter: 49,
  growth: 149,
  agency: 299,
  enterprise: 999,
}

export function estimateMrr(orgs = []) {
  return orgs
    .filter(o => o.subscription_status === 'active' && PLAN_PRICES[o.plan])
    .reduce((sum, o) => sum + PLAN_PRICES[o.plan], 0)
}

export function formatMoney(n) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

export function compactNumber(n) {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

export function unwrapList(data) {
  if (!data) return []
  if (Array.isArray(data)) return data
  if (Array.isArray(data.items)) return data.items
  if (Array.isArray(data.data)) return data.data
  return []
}

export function isActiveSubscription(org) {
  return org?.subscription_status === 'active'
}

export function getUserActive(user) {
  return user?.is_active !== false
}

export function getOrgTablesCount(org) {
  return org?.table_count ?? org?.tables_count ?? 0
}

export function getOrgSourcesCount(org) {
  return org?.source_count ?? org?.sources_count ?? 0
}
