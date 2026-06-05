import { useEffect, useState } from 'react'
import { RefreshCw, Server, Table2 } from 'lucide-react'
import { getIncidents, getSources, getTables } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import IncidentCard from '../components/IncidentCard'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, formatDateTime, formatNumber } from '../components/app-ui'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

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
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const load = async (isRefresh = false) => {
    setError('')
    if (isRefresh) setRefreshing(true)
    try {
      const [s, t, i] = await Promise.all([
        getSources(),
        getTables(),
        getIncidents({ status: 'open', limit: 20 }),
      ])
      setSources(s.data)
      setTables(t.data)
      setIncidents(i.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load overview data')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(() => load(true), 60000)
    return () => clearInterval(timer)
  }, [])

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
          <Button type="button" variant="outline" onClick={() => load(true)} disabled={refreshing}>
            <RefreshCw data-icon="inline-start" className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </Button>
        }
      />

      <ErrorNotice message={error} onDismiss={() => setError('')} />

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
