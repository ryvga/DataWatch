import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { AlertTriangle, CheckCircle2, ChevronRight, Clock, Database, ShieldAlert, Table2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getIncidents, getOrgHealth, getSources, getTables } from '../api/endpoints'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, formatNumber } from '../components/app-ui'
import RefreshBar from '../components/RefreshBar'
import { useAutoRefresh } from '../hooks/useAutoRefresh'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const HEALTH_RING_COLOR = { green: '#10b981', yellow: '#f59e0b', red: '#ef4444' }

function HealthRing({ score = 0, color = 'red', grade = '?' }) {
  const r = 38, c = 2 * Math.PI * r
  const offset = c - (Math.min(100, Math.max(0, score)) / 100) * c
  const stroke = HEALTH_RING_COLOR[color] || HEALTH_RING_COLOR.red

  return (
    <div className="relative size-28 shrink-0">
      <svg viewBox="0 0 88 88" className="size-28 -rotate-90">
        <circle cx="44" cy="44" r={r} fill="none" stroke="currentColor" strokeWidth="8" className="text-muted/30" />
        <circle
          cx="44"
          cy="44"
          r={r}
          fill="none"
          stroke={stroke}
          strokeWidth="8"
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-black tabular-nums" style={{ color: stroke }}>{Math.round(score)}</span>
        <span className="text-xs font-bold" style={{ color: stroke }}>{grade}</span>
      </div>
    </div>
  )
}

function StatCard({ label, value, subtitle, icon: Icon, accentColor, iconBg, iconColor }) {
  return (
    <Card className="relative overflow-hidden lg:col-span-1">
      <div className={`absolute top-0 inset-x-0 h-[3px] rounded-t-lg ${accentColor}`} />
      <CardContent className="pt-5 pb-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <p className="mt-1 text-3xl font-black tabular-nums leading-none">{value}</p>
            {subtitle && <p className="mt-1.5 text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          <div className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${iconBg}`}>
            <Icon className={`size-4 ${iconColor}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function Overview() {
  const [sources, setSources] = useState([])
  const [tables, setTables] = useState([])
  const [incidents, setIncidents] = useState([])
  const [orgHealth, setOrgHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [interval, setInterval_] = useState(30000)

  const load = async () => {
    setError('')
    try {
      const [s, t, i, h] = await Promise.all([
        getSources(),
        getTables(),
        getIncidents({ status: 'open', limit: 20 }),
        getOrgHealth().catch(() => null),
      ])
      setSources(s.data)
      setTables(t.data)
      setIncidents(i.data)
      if (h) setOrgHealth(h.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load overview data')
    } finally {
      setLoading(false)
    }
  }

  const { isRefreshing, lastRefreshed, refresh } = useAutoRefresh(load, interval, { enabled: interval > 0 })

  if (loading) return <LoadingState label="Loading overview" />

  const p1Incidents = incidents.filter((incident) => incident.severity === 'P1')
  const activeTables = tables.filter((table) => table.is_active)
  const connectedSources = sources.filter((source) => source.status === 'connected')

  const sortedIncidents = [...incidents].sort((a, b) => {
    const severity = { P1: 0, P2: 1, P3: 2 }
    return (severity[a.severity] ?? 3) - (severity[b.severity] ?? 3)
  })

  const stats = [
    {
      label: 'P1 Incidents',
      value: p1Incidents.length,
      subtitle: 'critical',
      icon: ShieldAlert,
      accentColor: 'bg-red-500',
      iconBg: 'bg-red-500/10',
      iconColor: 'text-red-500',
    },
    {
      label: 'Open Incidents',
      value: incidents.length,
      subtitle: incidents.length === 0 ? 'all clear' : 'need attention',
      icon: AlertTriangle,
      accentColor: 'bg-orange-500',
      iconBg: 'bg-orange-500/10',
      iconColor: 'text-orange-500',
    },
    {
      label: 'Monitored Tables',
      value: activeTables.length,
      subtitle: `${tables.length} total`,
      icon: Table2,
      accentColor: 'bg-primary',
      iconBg: 'bg-primary/10',
      iconColor: 'text-primary',
    },
    {
      label: 'Sources',
      value: `${connectedSources.length}/${sources.length}`,
      subtitle: 'connected',
      icon: Database,
      accentColor: 'bg-emerald-500',
      iconBg: 'bg-emerald-500/10',
      iconColor: 'text-emerald-500',
    },
  ]

  return (
    <div className="dw-page">
      {p1Incidents.length > 0 && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          <span className="inline-flex size-2 rounded-full bg-red-500 animate-pulse shrink-0" />
          <span className="font-semibold text-red-600 dark:text-red-400">
            {p1Incidents.length} critical incident{p1Incidents.length !== 1 ? 's' : ''}
          </span>
          <span className="text-muted-foreground">requires immediate attention</span>
          <Link
            to="/incidents?severity=P1"
            className="ml-auto text-xs font-medium text-red-600 dark:text-red-400 underline underline-offset-2 hover:no-underline"
          >
            View all
          </Link>
        </div>
      )}

      <PageHeader
        title="Overview"
        description={`${activeTables.length} active tables · ${incidents.length} open incident${incidents.length !== 1 ? 's' : ''}`}
        actions={
          <RefreshBar
            isRefreshing={isRefreshing}
            lastRefreshed={lastRefreshed}
            onRefresh={refresh}
            interval={interval}
            onIntervalChange={setInterval_}
          />
        }
      />

      <ErrorNotice message={error} onDismiss={() => setError('')} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Card className="relative col-span-2 overflow-hidden lg:col-span-1">
          <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent pointer-events-none" />
          {orgHealth ? (
            <CardContent className="relative flex flex-col items-center justify-center py-6 gap-1">
              <HealthRing score={orgHealth.score} color={orgHealth.color} grade={orgHealth.grade} />
              <p className="mt-1 text-sm font-semibold">Health Score</p>
              <p className="text-xs text-muted-foreground">Last 24h, weighted by severity</p>
            </CardContent>
          ) : (
            <CardContent className="relative flex flex-col items-center justify-center py-6 gap-2 text-center">
              <div className="flex size-28 items-center justify-center rounded-full border border-dashed bg-muted/30">
                <Clock className="size-7 text-muted-foreground" />
              </div>
              <p className="text-sm font-semibold">Health Score</p>
              <p className="text-xs text-muted-foreground">Waiting for organization health</p>
            </CardContent>
          )}
        </Card>

        {stats.map((stat) => (
          <StatCard key={stat.label} {...stat} />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Card className="flex flex-col">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <AlertTriangle className="size-4 text-muted-foreground" />
                Active Incidents
                {incidents.length > 0 && (
                  <span className="ml-1 rounded-full bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums">
                    {incidents.length}
                  </span>
                )}
              </CardTitle>
              <Link to="/incidents" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
                View all →
              </Link>
            </div>
          </CardHeader>
          <CardContent className="flex-1 p-0">
            {sortedIncidents.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="flex size-12 items-center justify-center rounded-full bg-emerald-500/10 mb-3">
                  <CheckCircle2 className="size-6 text-emerald-500" />
                </div>
                <p className="text-sm font-semibold">All clear</p>
                <p className="text-xs text-muted-foreground mt-1">No open incidents right now</p>
              </div>
            ) : (
              sortedIncidents.slice(0, 8).map((incident) => {
                const SEV_STYLE = {
                  P1: { bar: 'bg-red-500', text: 'text-red-500', bg: 'hover:bg-red-500/5' },
                  P2: { bar: 'bg-orange-500', text: 'text-orange-500', bg: 'hover:bg-orange-500/5' },
                  P3: { bar: 'bg-yellow-500', text: 'text-yellow-500', bg: 'hover:bg-yellow-500/5' },
                }
                const s = SEV_STYLE[incident.severity] || SEV_STYLE.P3

                return (
                  <Link
                    key={incident.id}
                    to={`/incidents/${incident.id}`}
                    className={`flex items-start gap-3 border-b px-4 py-3 last:border-b-0 transition-colors ${s.bg}`}
                  >
                    <div className={`mt-1 h-full w-[3px] self-stretch rounded-full shrink-0 ${s.bar}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className={`text-[11px] font-bold tracking-wide ${s.text}`}>{incident.severity}</span>
                        <span className="text-[11px] text-muted-foreground">
                          {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
                        </span>
                      </div>
                      <p className="text-sm font-medium text-foreground line-clamp-1">
                        {incident.title || 'Anomaly detected'}
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-0.5 capitalize">
                        {incident.status}
                      </p>
                    </div>
                    <ChevronRight className="size-4 text-muted-foreground shrink-0 mt-1" />
                  </Link>
                )
              })
            )}
          </CardContent>
        </Card>

        <Card className="flex flex-col">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <Table2 className="size-4 text-muted-foreground" />
                Monitored Tables
              </CardTitle>
              <Link to="/tables" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
                View all →
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {tables.slice(0, 10).map((table) => {
                const hasIncident = incidents.some((incident) => incident.table_id === table.id)
                const status = !table.is_active ? 'paused'
                  : table.latest_profile?.error ? 'error'
                    : hasIncident ? 'incident'
                      : 'healthy'
                const DOT = {
                  healthy: 'bg-emerald-500',
                  incident: 'bg-orange-500 ring-2 ring-orange-500/30',
                  error: 'bg-red-500 ring-2 ring-red-500/30',
                  paused: 'bg-muted-foreground/40',
                }
                const BORDER = {
                  healthy: 'hover:border-border hover:bg-muted/30',
                  incident: 'border-orange-500/30 bg-orange-500/5 hover:border-orange-500/50',
                  error: 'border-red-500/30 bg-red-500/5 hover:border-red-500/50',
                  paused: 'opacity-60 hover:bg-muted/20',
                }

                return (
                  <Link
                    key={table.id}
                    to={`/tables/${table.id}`}
                    className={`flex items-center gap-3 rounded-lg border bg-card p-3 transition-all ${BORDER[status]}`}
                  >
                    <div className={`size-2 rounded-full shrink-0 ${DOT[status]}`} />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-mono font-semibold truncate leading-tight">
                        {table.schema_name}.{table.table_name}
                      </p>
                      <p className="text-[11px] text-muted-foreground leading-tight mt-0.5">
                        {formatNumber(table.latest_profile?.row_count)} rows
                      </p>
                    </div>
                    {status === 'incident' && <AlertTriangle className="size-3.5 text-orange-500 shrink-0" />}
                    {status === 'error' && <AlertTriangle className="size-3.5 text-red-500 shrink-0" />}
                  </Link>
                )
              })}
            </div>
            {tables.length === 0 && (
              <EmptyState
                icon={Table2}
                title="No tables monitored"
                description="Add monitored tables after connecting a data source."
              />
            )}
          </CardContent>
        </Card>
      </div>

      {sources.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-2">
            <Database className="size-4" />
            Data Sources
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {sources.map((source) => {
              const sourceTables = tables.filter((table) => table.source_id === source.id)
              const healthyCount = sourceTables.filter((table) => !table.latest_profile?.error).length
              const connected = source.status === 'connected'

              return (
                <div key={source.id} className="flex items-center gap-4 rounded-xl border bg-card px-4 py-3">
                  <div className="relative shrink-0">
                    <div className={`size-2.5 rounded-full ${connected ? 'bg-emerald-500' : 'bg-red-500'}`} />
                    {connected && (
                      <div className="absolute inset-0 size-2.5 rounded-full bg-emerald-500 animate-ping opacity-40" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold truncate">{source.name}</p>
                    <p className="text-xs text-muted-foreground capitalize">{source.type}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-semibold tabular-nums">{healthyCount}/{sourceTables.length}</p>
                    <p className="text-[11px] text-muted-foreground">tables ok</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
