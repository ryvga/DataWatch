import { useEffect, useState } from 'react'
import { Activity, AlertTriangle, CheckCircle2, Server, Table2 } from 'lucide-react'
import { getIncidents, getOrgHealth, getSources, getTables } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import IncidentCard from '../components/IncidentCard'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, formatDateTime, formatNumber } from '../components/app-ui'
import RefreshBar from '../components/RefreshBar'
import { useAutoRefresh } from '../hooks/useAutoRefresh'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const HEALTH_RING_COLOR = { green: '#10b981', yellow: '#f59e0b', red: '#ef4444' }

function HealthRing({ score = 0, color = 'red', grade = '?' }) {
  const r = 38, c = 2 * Math.PI * r
  const offset = c - (Math.min(100, Math.max(0, score)) / 100) * c
  const stroke = HEALTH_RING_COLOR[color] || HEALTH_RING_COLOR.red
  return (
    <div className="flex items-center gap-4">
      <div className="relative size-24 shrink-0">
        <svg viewBox="0 0 88 88" className="size-24 -rotate-90">
          <circle cx="44" cy="44" r={r} fill="none" stroke="currentColor" strokeWidth="8" className="text-muted/30" />
          <circle cx="44" cy="44" r={r} fill="none" stroke={stroke} strokeWidth="8"
            strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 0.6s ease' }} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-black tabular-nums" style={{ color: stroke }}>{Math.round(score)}</span>
          <span className="text-xs font-bold" style={{ color: stroke }}>{grade}</span>
        </div>
      </div>
      <div>
        <p className="text-sm font-semibold">Health Score</p>
        <p className="text-xs text-muted-foreground mt-0.5">Last 24h, weighted by severity</p>
      </div>
    </div>
  )
}

function SourceHealthRow({ source, tables }) {
  const healthy = tables.filter((table) => !table.latest_profile?.error).length
  const total = tables.length
  const pct = total ? Math.round((healthy / total) * 100) : 0
  const status = source.status === 'connected' ? 'connected' : 'error'

  return (
    <TableRow>
      <TableCell>
        <div className="font-medium">{source.name}</div>
        <div className="text-xs text-muted-foreground">{source.type}</div>
      </TableCell>
      <TableCell>
        <HealthBadge status={status} />
      </TableCell>
      <TableCell className="text-right text-sm text-muted-foreground">{healthy}/{total}</TableCell>
    </TableRow>
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

  const sortedIncidents = [...incidents].sort((a, b) => {
    const severity = { P1: 0, P2: 1, P3: 2 }
    return (severity[a.severity] ?? 3) - (severity[b.severity] ?? 3)
  })

  return (
    <div className="dw-page">
      <PageHeader
        title="Overview"
        description={`${tables.length} monitored tables · ${incidents.length} open incident${incidents.length !== 1 ? 's' : ''}`}
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

      {/* ── Health + Stats row ─── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {orgHealth ? (
          <Card className="sm:col-span-2 lg:col-span-1">
            <CardContent className="pt-5">
              <HealthRing score={orgHealth.score} color={orgHealth.color} grade={orgHealth.grade} />
            </CardContent>
          </Card>
        ) : null}
        {[
          { label: 'Open incidents', value: incidents.filter(i => i.status === 'open').length, icon: AlertTriangle, color: incidents.some(i => i.severity === 'P1') ? 'text-red-500' : 'text-orange-500' },
          { label: 'Monitored tables', value: tables.length, icon: Table2, color: 'text-primary' },
          { label: 'Sources connected', value: sources.filter(s => s.status === 'connected').length, icon: Server, color: 'text-emerald-500' },
        ].map(stat => (
          <Card key={stat.label}>
            <CardContent className="flex min-h-[88px] items-start justify-between pt-5">
              <div>
                <p className="text-xs text-muted-foreground">{stat.label}</p>
                <p className="mt-1 text-3xl font-black tabular-nums">{stat.value}</p>
              </div>
              <stat.icon className={`size-5 mt-1 ${stat.color}`} />
            </CardContent>
          </Card>
        ))}
        {!orgHealth && (
          <Card>
            <CardContent className="flex min-h-[88px] items-start justify-between pt-5">
              <div>
                <p className="text-xs text-muted-foreground">Checks passed (24h)</p>
                <p className="mt-1 text-3xl font-black tabular-nums">—</p>
              </div>
              <CheckCircle2 className="size-5 mt-1 text-emerald-500" />
            </CardContent>
          </Card>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(320px,0.55fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="size-4 text-muted-foreground" />
              Data sources
            </CardTitle>
          </CardHeader>
          <CardContent>
            {sources.length === 0 ? (
              <EmptyState icon={Server} title="No data sources" description="Connect a warehouse in Settings to start monitoring." />
            ) : (
              <div className="dw-table-wrap">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Source</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Tables</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sources.map((source) => (
                      <SourceHealthRow key={source.id} source={source} tables={tables.filter((table) => table.source_id === source.id)} />
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Active incidents</CardTitle>
          </CardHeader>
          <CardContent>
            {sortedIncidents.length === 0 ? (
              <EmptyState title="No open incidents" description="Current table profiles are not reporting open anomalies." />
            ) : (
              <div className="overflow-hidden rounded-lg border">
                {sortedIncidents.map((incident) => (
                  <IncidentCard key={incident.id} incident={incident} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Table2 className="size-4 text-muted-foreground" />
            Monitored tables
          </CardTitle>
        </CardHeader>
        <CardContent>
          {tables.length === 0 ? (
            <EmptyState icon={Table2} title="No tables monitored" description="Add monitored tables after connecting a data source." />
          ) : (
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Table</TableHead>
                    <TableHead>Rows</TableHead>
                    <TableHead className="hidden sm:table-cell">Last profile</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tables.slice(0, 12).map((table) => {
                    const hasIncident = incidents.some(i => i.table_id === table.id)
                    const status = !table.is_active ? 'paused' : table.latest_profile?.error ? 'error' : hasIncident ? 'incident' : 'healthy'
                    return (
                      <TableRow key={table.id} className="cursor-pointer hover:bg-muted/30" onClick={() => window.location.href = `/tables/${table.id}`}>
                        <TableCell className="font-mono text-xs">{table.schema_name}.{table.table_name}</TableCell>
                        <TableCell className="tabular-nums text-muted-foreground">{formatNumber(table.latest_profile?.row_count)}</TableCell>
                        <TableCell className="text-xs text-muted-foreground hidden sm:table-cell">{formatDateTime(table.last_profiled_at)}</TableCell>
                        <TableCell><HealthBadge status={status} /></TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
