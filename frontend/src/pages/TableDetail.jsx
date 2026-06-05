import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Play } from 'lucide-react'
import { getChecks, getIncidents, getProfiles, getTable, runTable } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import MetricChart from '../components/MetricChart'
import SeverityBadge from '../components/SeverityBadge'
import { EmptyState, LoadingState, PageHeader, formatDateTime, formatNumber } from '../components/app-ui'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

export default function TableDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [table, setTable] = useState(null)
  const [profiles, setProfiles] = useState([])
  const [checks, setChecks] = useState([])
  const [incidents, setIncidents] = useState([])
  const [selectedCol, setSelectedCol] = useState(null)
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getTable(id),
      getProfiles(id, { limit: 30 }),
      getChecks(id, { limit: 100 }),
      getIncidents({ table_id: id, limit: 20 }),
    ]).then(([tableResponse, profilesResponse, checksResponse, incidentsResponse]) => {
      setTable(tableResponse.data)
      setProfiles(profilesResponse.data)
      setChecks(checksResponse.data)
      setIncidents(incidentsResponse.data)
      const columns = Object.keys(tableResponse.data.latest_profile?.column_metrics || {})
      if (columns.length) setSelectedCol(columns[0])
    }).finally(() => setLoading(false))
  }, [id])

  const handleRun = async () => {
    setRunning(true)
    try {
      await runTable(id)
    } catch (_) {
    } finally {
      setTimeout(() => setRunning(false), 2000)
    }
  }

  if (loading) return <LoadingState label="Loading table detail" />
  if (!table) return <div className="dw-page text-destructive">Table not found</div>

  const latestProfile = table.latest_profile
  const allCols = Object.keys(latestProfile?.column_metrics || {})
  const anomalousProfileIds = new Set(checks.filter((check) => check.status === 'failed').map((check) => check.profile_id))
  const anomalousDots = profiles.filter((profile) => anomalousProfileIds.has(profile.id))

  return (
    <div className="dw-page">
      <Button type="button" variant="ghost" className="w-fit" onClick={() => nav(-1)}>
        <ArrowLeft data-icon="inline-start" />
        Back
      </Button>

      <PageHeader
        title={`${table.schema_name}.${table.table_name}`}
        description={`Every ${table.check_interval_minutes}m${latestProfile ? `, ${formatNumber(latestProfile.row_count)} rows, last profiled ${formatDateTime(table.last_profiled_at)}` : ''}`}
        actions={
          <>
            <HealthBadge status={table.is_active ? 'healthy' : 'paused'} size="lg" />
            <Button type="button" onClick={handleRun} disabled={running}>
              <Play data-icon="inline-start" />
              {running ? 'Queued' : 'Run now'}
            </Button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Row count, 30 profiles</CardTitle>
          </CardHeader>
          <CardContent>
            <MetricChart data={profiles} dataKey="row_count" anomalies={anomalousDots} label="rows" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Freshness seconds</CardTitle>
          </CardHeader>
          <CardContent>
            <MetricChart data={profiles} dataKey="freshness_seconds" color="hsl(var(--chart-2))" label="seconds" />
          </CardContent>
        </Card>
        {allCols.length > 0 && (
          <Card className="lg:col-span-2">
            <CardHeader className="flex-row items-center justify-between gap-3">
              <CardTitle className="text-base">Null rate</CardTitle>
              <Select value={selectedCol || ''} onValueChange={setSelectedCol}>
                <SelectTrigger className="w-56">
                  <SelectValue placeholder="Select column" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {allCols.map((column) => (
                      <SelectItem key={column} value={column}>{column}</SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </CardHeader>
            <CardContent>
              <MetricChart
                data={profiles.map((profile) => ({
                  ...profile,
                  null_rate: profile.column_metrics?.[selectedCol]?.null_rate,
                }))}
                dataKey="null_rate"
                color="hsl(var(--chart-3))"
                label="null rate"
              />
            </CardContent>
          </Card>
        )}
      </div>

      {latestProfile?.column_metrics && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Column health</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    {['Column', 'Null rate', 'Distinct', 'Min', 'Max', 'Mean'].map((header) => (
                      <TableHead key={header}>{header}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allCols.map((column) => {
                    const metric = latestProfile.column_metrics[column] || {}
                    const nullRate = metric.null_rate ?? null
                    return (
                      <TableRow key={column}>
                        <TableCell className="font-mono text-xs">{column}</TableCell>
                        <TableCell className="tabular-nums">{nullRate !== null ? `${(nullRate * 100).toFixed(1)}%` : '—'}</TableCell>
                        <TableCell className="text-muted-foreground">{formatNumber(metric.distinct_count)}</TableCell>
                        <TableCell className="max-w-36 truncate text-muted-foreground">{metric.min ?? '—'}</TableCell>
                        <TableCell className="max-w-36 truncate text-muted-foreground">{metric.max ?? '—'}</TableCell>
                        <TableCell className="text-muted-foreground">{metric.mean != null ? Number(metric.mean).toFixed(2) : '—'}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Incident history</CardTitle>
        </CardHeader>
        <CardContent>
          {incidents.length === 0 ? (
            <EmptyState title="No incidents for this table" description="Profiles have not created incidents for this table yet." />
          ) : (
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Severity</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {incidents.map((incident) => (
                    <TableRow key={incident.id} className="cursor-pointer" onClick={() => nav(`/incidents/${incident.id}`)}>
                      <TableCell><SeverityBadge severity={incident.severity} /></TableCell>
                      <TableCell className="font-medium">{incident.title}</TableCell>
                      <TableCell><HealthBadge status={incident.status} /></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDateTime(incident.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
