import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Play } from 'lucide-react'
import { getIncidents, getSources, getTable, getTableCheckResults, getTableProfiles, runTable } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import MetricChart from '../components/MetricChart'
import SeverityBadge from '../components/SeverityBadge'
import { EmptyState, LoadingState, PageHeader, formatDateTime, formatNumber } from '../components/app-ui'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const NULL_RATE_STYLES = {
  good: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  warning: 'border-amber-600/25 bg-amber-500/12 text-amber-700 dark:text-amber-300',
  bad: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  unknown: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

function formatPercent(value, digits = 1) {
  return value == null ? '-' : `${(Number(value) * 100).toFixed(digits)}%`
}

function formatMetricValue(value) {
  if (value == null || value === '') return '-'
  if (typeof value === 'number') return Number.isInteger(value) ? formatNumber(value) : value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return String(value)
}

function nullRateTone(value) {
  if (value == null) return 'unknown'
  if (value < 0.01) return 'good'
  if (value <= 0.05) return 'warning'
  return 'bad'
}

function inferTypeHint(metric = {}) {
  if (['mean', 'stddev', 'p25', 'p50', 'p75', 'p95', 'zero_rate', 'negative_rate'].some((key) => metric[key] != null)) return 'numeric'
  if (metric.range_seconds != null) return 'timestamp'
  if (['min_len', 'max_len', 'avg_len', 'empty_rate'].some((key) => metric[key] != null)) return 'text'
  const values = [metric.min, metric.max].filter(Boolean)
  if (values.some((value) => !Number.isNaN(Date.parse(value)))) return 'timestamp'
  return 'text'
}

function formatTopValues(metric = {}) {
  const values = metric.top_values ?? metric.top_values_count ?? metric.value_counts ?? metric.most_common
  if (!values) return '-'
  if (Array.isArray(values)) {
    return values
      .slice(0, 3)
      .map((item) => {
        if (Array.isArray(item)) return `${formatMetricValue(item[0])} (${formatNumber(item[1])})`
        if (item && typeof item === 'object') return `${formatMetricValue(item.value ?? item.key)} (${formatNumber(item.count ?? item.frequency)})`
        return formatMetricValue(item)
      })
      .join(', ')
  }
  if (typeof values === 'object') {
    return Object.entries(values)
      .slice(0, 3)
      .map(([value, count]) => `${formatMetricValue(value)} (${formatNumber(count)})`)
      .join(', ')
  }
  return formatMetricValue(values)
}

function StatCard({ label, value, detail, trend }) {
  const TrendIcon = trend?.direction === 'up' ? ArrowUp : trend?.direction === 'down' ? ArrowDown : ArrowRight

  return (
    <Card size="sm">
      <CardContent className="flex min-h-28 flex-col justify-between gap-3">
        <div className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{label}</div>
        <div>
          <div className="break-words text-xl font-semibold tabular-nums text-foreground">{value}</div>
          {detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}
        </div>
        {trend && (
          <div className={trend.className}>
            <TrendIcon className="size-3.5" />
            <span>{trend.label}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function TableDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [table, setTable] = useState(null)
  const [sources, setSources] = useState([])
  const [profiles, setProfiles] = useState([])
  const [checks, setChecks] = useState([])
  const [incidents, setIncidents] = useState([])
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getTable(id),
      getSources(),
      getTableProfiles(id, { limit: 30 }),
      getTableCheckResults(id, { limit: 100 }),
      getIncidents({ table_id: id, limit: 100 }),
    ]).then(([tableResponse, sourcesResponse, profilesResponse, checksResponse, incidentsResponse]) => {
      setTable(tableResponse.data)
      setSources(sourcesResponse.data)
      setProfiles(profilesResponse.data)
      setChecks(checksResponse.data)
      setIncidents(incidentsResponse.data)
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

  const profileSeries = useMemo(
    () => [...profiles].sort((a, b) => new Date(a.collected_at) - new Date(b.collected_at)),
    [profiles]
  )
  const profilesDesc = useMemo(
    () => [...profiles].sort((a, b) => new Date(b.collected_at) - new Date(a.collected_at)),
    [profiles]
  )

  if (loading) return <LoadingState label="Loading table detail" />
  if (!table) return <div className="dw-page text-destructive">Table not found</div>

  const latestProfile = table.latest_profile
  const source = sources.find((item) => item.id === table.source_id)
  const sourceName = table.source_name || table.source?.name || source?.name || table.source_id
  const columnMetrics = latestProfile?.column_metrics || {}
  const columnRows = Object.entries(columnMetrics)
    .map(([name, metric]) => ({ name, metric: metric || {}, nullRate: metric?.null_rate ?? null }))
    .sort((a, b) => (b.nullRate ?? -1) - (a.nullRate ?? -1))
  const nullRates = columnRows.map((row) => row.nullRate).filter((value) => value != null)
  const avgNullRate = nullRates.length ? nullRates.reduce((sum, value) => sum + Number(value), 0) / nullRates.length : null
  const activeIncidents = incidents.filter((incident) => incident.status !== 'resolved')
  const anomalousProfileIds = new Set(checks.filter((check) => check.status === 'failed').map((check) => check.profile_id))
  const anomalousDots = profileSeries.filter((profile) => anomalousProfileIds.has(profile.id))
  const previousProfile = profilesDesc.find((profile) => profile.id !== latestProfile?.id && profile.row_count != null)
  const rowDelta = latestProfile?.row_count != null && previousProfile?.row_count != null ? latestProfile.row_count - previousProfile.row_count : null
  const rowDeltaPct = rowDelta != null && previousProfile.row_count !== 0 ? rowDelta / previousProfile.row_count : null
  const latestChecks = checks
    .filter((check) => !latestProfile?.id || check.profile_id === latestProfile.id)
    .slice(0, 10)
  const rowTrend = rowDelta == null ? null : {
    direction: rowDelta > 0 ? 'up' : rowDelta < 0 ? 'down' : 'flat',
    label: `${rowDelta > 0 ? '+' : ''}${formatNumber(rowDelta)} (${rowDeltaPct == null ? '-' : formatPercent(rowDeltaPct)}) vs previous`,
    className: rowDelta > 0
      ? 'inline-flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-300'
      : rowDelta < 0
        ? 'inline-flex items-center gap-1 text-xs text-red-700 dark:text-red-300'
        : 'inline-flex items-center gap-1 text-xs text-muted-foreground',
  }

  return (
    <div className="dw-page">
      <Button type="button" variant="ghost" className="w-fit" onClick={() => nav(-1)}>
        <ArrowLeft data-icon="inline-start" />
        Back
      </Button>

      <PageHeader
        title={`${table.schema_name}.${table.table_name}`}
        description={`${sourceName} - Every ${table.check_interval_minutes}m${latestProfile ? ` - Last profiled ${formatDateTime(table.last_profiled_at || latestProfile.collected_at)}` : ''}`}
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

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Row Count" value={formatNumber(latestProfile?.row_count)} detail="Latest profile" trend={rowTrend} />
        <StatCard label="Freshness" value={formatDateTime(table.last_profiled_at || latestProfile?.collected_at)} detail="Last profiled at" />
        <StatCard label="Null Rate" value={formatPercent(avgNullRate)} detail={`Average across ${formatNumber(columnRows.length)} columns`} />
        <StatCard label="Active Incidents" value={formatNumber(activeIncidents.length)} detail={`${formatNumber(incidents.length)} total incidents`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Row count, 30 profiles</CardTitle>
          </CardHeader>
          <CardContent>
            <MetricChart data={profileSeries} dataKey="row_count" anomalies={anomalousDots} label="rows" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Profile history</CardTitle>
          </CardHeader>
          <CardContent>
            <MetricChart data={profileSeries} dataKey="freshness_seconds" color="hsl(var(--chart-2))" label="seconds" />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Column metrics</CardTitle>
        </CardHeader>
        <CardContent>
          {columnRows.length === 0 ? (
            <EmptyState title="No column metrics yet" description="The latest profile has not captured column-level metrics." />
          ) : (
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Column Name</TableHead>
                    <TableHead>Type hint</TableHead>
                    <TableHead>Null Rate</TableHead>
                    <TableHead>Distinct Count</TableHead>
                    <TableHead>Top Values</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {columnRows.map(({ name, metric, nullRate }) => (
                    <TableRow key={name}>
                      <TableCell className="font-mono text-xs">{name}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">{inferTypeHint(metric)}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={NULL_RATE_STYLES[nullRateTone(nullRate)]}>
                          {formatPercent(nullRate)}
                        </Badge>
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">{formatNumber(metric.distinct_count)}</TableCell>
                      <TableCell className="max-w-[28rem] truncate text-muted-foreground">{formatTopValues(metric)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Check results</CardTitle>
        </CardHeader>
        <CardContent>
          {latestChecks.length === 0 ? (
            <EmptyState title="No check results for the latest profile" description="Checks have not completed for this profile yet." />
          ) : (
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Check</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Observed Value</TableHead>
                    <TableHead>Checked At</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {latestChecks.map((check) => (
                    <TableRow key={check.id}>
                      <TableCell className="font-mono text-xs">{check.check_name}</TableCell>
                      <TableCell><HealthBadge status={check.status} /></TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">{formatMetricValue(check.observed_value)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDateTime(check.checked_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

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
