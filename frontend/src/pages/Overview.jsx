import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { AlertTriangle, CheckCircle2, ChevronRight, Database, Table2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getIncidents, getOrgHealth, getSources, getTables } from '../api/endpoints'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, formatNumber } from '../components/app-ui'
import RefreshBar from '../components/RefreshBar'
import SeverityBadge from '../components/SeverityBadge'
import { useAutoRefresh } from '../hooks/useAutoRefresh'
import { useRealtime } from '../hooks/useRealtime'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

function profileCountLabel(profile) {
  const countMode = profile?.profile_provenance?.count_mode
  if (countMode === 'estimated') return `≈${formatNumber(profile.row_count)} documents`
  if (countMode === 'lower_bound') return `≥${formatNumber(profile.row_count)} keys observed`
  return `${formatNumber(profile?.row_count)} rows`
}

function sourceStatus(source) {
  return source.status === 'connected' ? 'Connected' : source.status || 'Needs attention'
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
      setError(err.response?.data?.detail || err.message || 'Failed to load operational data')
    } finally {
      setLoading(false)
    }
  }

  const { isRefreshing, lastRefreshed, refresh } = useAutoRefresh(load, interval, { enabled: interval > 0 })

  useRealtime((event) => {
    if (['incident.updated', 'profile.completed', 'alert.dispatched', 'monitor.run.completed'].includes(event?.type)) load()
  })

  if (loading) return <LoadingState label="Loading operations" />

  const activeTables = tables.filter((table) => table.is_active)
  const connectedSources = sources.filter((source) => source.status === 'connected')
  const sortedIncidents = [...incidents].sort((a, b) => {
    const severity = { P1: 0, P2: 1, P3: 2 }
    return (severity[a.severity] ?? 3) - (severity[b.severity] ?? 3)
  })
  const criticalIncident = sortedIncidents.find((incident) => incident.severity === 'P1')
  const criticalCount = sortedIncidents.filter((incident) => incident.severity === 'P1').length

  return (
    <div className="dw-page gap-5">
      <PageHeader
        title="Operations"
        description={`${activeTables.length} monitored tables · ${connectedSources.length}/${sources.length} sources connected`}
        actions={<RefreshBar isRefreshing={isRefreshing} lastRefreshed={lastRefreshed} onRefresh={refresh} interval={interval} onIntervalChange={setInterval_} />}
      />

      <ErrorNotice message={error} onDismiss={() => setError('')} />

      {criticalIncident && (
        <div className="flex flex-col gap-3 border border-red-500/35 bg-red-500/8 px-4 py-3 sm:flex-row sm:items-center">
          <div className="flex min-w-0 items-center gap-3">
            <AlertTriangle className="size-4 shrink-0 text-red-600 dark:text-red-400" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-red-700 dark:text-red-300">{criticalCount} critical incident{criticalCount === 1 ? '' : 's'} need review</p>
              <p className="truncate text-xs text-muted-foreground">{criticalIncident.title || 'Anomaly detected'}</p>
            </div>
          </div>
          <Button asChild size="sm" variant="outline" className="border-red-500/35 text-red-700 hover:bg-red-500/10 dark:text-red-300 sm:ml-auto">
            <Link to={`/incidents/${criticalIncident.id}`}>Open incident</Link>
          </Button>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(19rem,0.85fr)]">
        <Card>
          <CardHeader className="border-b pb-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle>Incident queue</CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">Ordered by severity. Open the first item to begin investigation.</p>
              </div>
              <Button asChild size="sm" variant="ghost" className="shrink-0"><Link to="/incidents">All incidents</Link></Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {sortedIncidents.length === 0 ? (
              <div className="flex items-center gap-3 px-4 py-8 text-sm">
                <CheckCircle2 className="size-5 text-emerald-600" />
                <div><p className="font-medium">No open incidents</p><p className="text-xs text-muted-foreground">Monitoring is currently clear.</p></div>
              </div>
            ) : sortedIncidents.slice(0, 7).map((incident) => (
              <Link key={incident.id} to={`/incidents/${incident.id}`} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b px-4 py-3 last:border-b-0 hover:bg-muted/45">
                <SeverityBadge severity={incident.severity} />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{incident.title || 'Anomaly detected'}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{incident.status} · {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}</p>
                </div>
                <ChevronRight className="size-4 text-muted-foreground" />
              </Link>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b pb-3"><CardTitle>Monitoring state</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="border-l-2 border-primary pl-3"><p className="text-2xl font-semibold tabular-nums">{activeTables.length}</p><p className="text-xs text-muted-foreground">Active tables</p></div>
              <div className="border-l-2 border-emerald-600 pl-3"><p className="text-2xl font-semibold tabular-nums">{connectedSources.length}</p><p className="text-xs text-muted-foreground">Connected sources</p></div>
            </div>
            <div className="border-t pt-3">
              <div className="flex items-center justify-between gap-3 text-sm"><span className="text-muted-foreground">Health score</span><span className="font-semibold tabular-nums">{orgHealth ? `${Math.round(orgHealth.score)}/100` : 'Calculating'}</span></div>
              <p className="mt-1 text-xs text-muted-foreground">Weighted from the last 24 hours of monitored activity.</p>
            </div>
            <Button asChild className="w-full" variant="outline"><Link to="/tables">Review monitored tables</Link></Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="border-b pb-3">
          <div className="flex items-center justify-between gap-3"><div><CardTitle>Monitored assets</CardTitle><p className="mt-1 text-xs text-muted-foreground">Latest profile snapshot for each configured table.</p></div><Button asChild size="sm" variant="ghost"><Link to="/tables">Manage tables</Link></Button></div>
        </CardHeader>
        <CardContent className="p-0">
          {tables.length === 0 ? <div className="p-4"><EmptyState icon={Table2} title="No tables monitored" description="Connect a source, then add the first table to start profiling." /></div> : (
            <div className="divide-y">
              {tables.slice(0, 8).map((table) => {
                const hasIncident = incidents.some((incident) => incident.table_id === table.id)
                const state = !table.is_active ? 'Paused' : table.latest_profile?.error ? 'Profile error' : hasIncident ? 'Incident open' : 'Healthy'
                return <Link key={table.id} to={`/tables/${table.id}`} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3 hover:bg-muted/45 sm:grid-cols-[minmax(0,1fr)_9rem_8rem_auto]">
                  <div className="min-w-0"><p className="truncate font-mono text-sm font-medium">{table.schema_name}.{table.table_name}</p><p className="mt-0.5 truncate text-xs text-muted-foreground">{profileCountLabel(table.latest_profile)}</p></div>
                  <p className="hidden text-xs text-muted-foreground sm:block">{table.freshness_column || 'No freshness field'}</p>
                  <p className="hidden text-xs text-muted-foreground sm:block">
                    {table.check_interval_minutes ? `Every ${table.check_interval_minutes} min` : 'Schedule not set'}
                  </p>
                  <span className="text-xs font-medium text-muted-foreground">{state}</span>
                </Link>
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {sources.length > 0 && <div>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold"><Database className="size-4" /> Sources</div>
        <div className="grid gap-px border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {sources.map((source) => <Link key={source.id} to="/settings?tab=sources" className="bg-card px-4 py-3 hover:bg-muted/45"><p className="truncate text-sm font-medium">{source.name}</p><p className="mt-1 text-xs text-muted-foreground">{source.type} · {sourceStatus(source)}</p></Link>)}
        </div>
      </div>}
    </div>
  )
}
