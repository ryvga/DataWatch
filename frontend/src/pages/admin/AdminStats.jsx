import { useEffect, useMemo, useState } from 'react'
import { Activity, Building2, Database, Loader2, Table2, Users } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { toast } from 'sonner'
import { adminGetAllUsers, adminGetOrgs, adminGetStats } from '../../api/endpoints'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { compactNumber, estimateMrr, formatMoney, getOrgSourcesCount, getOrgTablesCount, getUserActive, isActiveSubscription, unwrapList } from './adminUtils.jsx'

function Metric({ icon: Icon, label, value, detail }) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3 p-4">
        <div className="rounded-md border bg-muted/45 p-2">
          <Icon className="size-4 text-muted-foreground" />
        </div>
        <div>
          <div className="text-xs font-medium text-muted-foreground">{label}</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
          {detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}
        </div>
      </CardContent>
    </Card>
  )
}

function startOfWeek(date) {
  const copy = new Date(date)
  const day = copy.getDay()
  copy.setHours(0, 0, 0, 0)
  copy.setDate(copy.getDate() - day)
  return copy
}

function withinDays(value, days) {
  if (!value) return false
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return false
  return Date.now() - date.getTime() <= days * 24 * 60 * 60 * 1000
}

function buildWeeklySeries(orgs) {
  const currentWeek = startOfWeek(new Date())
  const weeks = Array.from({ length: 8 }, (_, index) => {
    const start = new Date(currentWeek)
    start.setDate(currentWeek.getDate() - (7 - index) * 7)
    return {
      key: start.toISOString().slice(0, 10),
      label: start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      orgs: 0,
    }
  })
  const byKey = new Map(weeks.map((week) => [week.key, week]))
  orgs.forEach((org) => {
    const created = new Date(org.created_at)
    if (Number.isNaN(created.getTime())) return
    const weekKey = startOfWeek(created).toISOString().slice(0, 10)
    if (byKey.has(weekKey)) byKey.get(weekKey).orgs += 1
  })
  return weeks
}

export default function AdminStats() {
  const [orgs, setOrgs] = useState([])
  const [users, setUsers] = useState([])
  const [serverStats, setServerStats] = useState({})
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    const [statsResult, orgsResult, usersResult] = await Promise.allSettled([
      adminGetStats(),
      adminGetOrgs(),
      adminGetAllUsers(),
    ])

    if (statsResult.status === 'fulfilled') setServerStats(statsResult.value.data || {})
    if (orgsResult.status === 'fulfilled') {
      setOrgs(unwrapList(orgsResult.value.data).items)
    } else {
      toast.error(orgsResult.reason?.response?.data?.detail || 'Failed to load organizations')
    }
    if (usersResult.status === 'fulfilled') setUsers(unwrapList(usersResult.value.data).items)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const metrics = useMemo(() => {
    const orgs7d = orgs.filter((org) => withinDays(org.created_at, 7)).length
    const orgs30d = orgs.filter((org) => withinDays(org.created_at, 30)).length
    const users7d = users.filter((user) => withinDays(user.last_login_at, 7)).length
    return {
      mrr: serverStats.mrr ?? estimateMrr(orgs),
      activeSubscriptions: serverStats.active_subscriptions_count ?? orgs.filter((org) => isActiveSubscription(org.subscription_status)).length,
      newOrgs7d: serverStats.new_orgs_last_7d ?? orgs7d,
      newOrgs30d: serverStats.new_orgs_last_30d ?? orgs30d,
      activeUsers7d: serverStats.active_users_last_7d ?? users7d,
      totalOrgs: serverStats.total_orgs ?? orgs.length,
      totalUsers: serverStats.total_users ?? users.length,
      totalSources: serverStats.total_sources ?? orgs.reduce((sum, org) => sum + getOrgSourcesCount(org), 0),
      totalTables: serverStats.total_tables ?? orgs.reduce((sum, org) => sum + getOrgTablesCount(org), 0),
      incidents7d: serverStats.incidents_last_7d ?? 0,
      activeUsers: users.filter(getUserActive).length,
    }
  }, [orgs, users, serverStats])

  const chartData = useMemo(() => serverStats.new_orgs_by_week || buildWeeklySeries(orgs), [orgs, serverStats])

  if (loading && orgs.length === 0) {
    return <div className="flex justify-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Admin dashboard</h1>
          <p className="text-sm text-muted-foreground">Revenue, tenant growth, account activity, and platform inventory.</p>
        </div>
        <button className="text-sm text-primary hover:underline" onClick={load} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Metric icon={Activity} label="MRR estimate" value={formatMoney(metrics.mrr)} detail="Plan price × active orgs" />
        <Metric icon={Building2} label="Active subscriptions" value={compactNumber(metrics.activeSubscriptions)} detail={`${compactNumber(metrics.newOrgs7d)} new orgs in 7d`} />
        <Metric icon={Users} label="Active users last 7d" value={compactNumber(metrics.activeUsers7d)} detail={`${compactNumber(metrics.activeUsers)} active accounts total`} />
        <Metric icon={Building2} label="New orgs last 30d" value={compactNumber(metrics.newOrgs30d)} detail={`${compactNumber(metrics.newOrgs7d)} in the last 7 days`} />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <Metric icon={Building2} label="Total orgs" value={compactNumber(metrics.totalOrgs)} />
        <Metric icon={Users} label="Total users" value={compactNumber(metrics.totalUsers)} />
        <Metric icon={Database} label="Total sources" value={compactNumber(metrics.totalSources)} />
        <Metric icon={Table2} label="Total tables" value={compactNumber(metrics.totalTables)} />
        <Metric icon={Activity} label="Incidents last 7d" value={compactNumber(metrics.incidents7d)} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">New organizations by week</CardTitle>
          <CardDescription>Last 8 weeks, grouped by week start.</CardDescription>
        </CardHeader>
        <CardContent className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} width={32} />
              <Tooltip
                cursor={{ fill: 'hsl(var(--muted))' }}
                contentStyle={{
                  background: 'hsl(var(--popover))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: 8,
                  color: 'hsl(var(--popover-foreground))',
                }}
              />
              <Bar dataKey="orgs" name="New orgs" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  )
}
