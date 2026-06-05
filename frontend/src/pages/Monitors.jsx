import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { getSources, getTables } from '../api/endpoints'
import { EmptyState, LoadingState, PageHeader, formatDateTime } from '../components/app-ui'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const CHECK_BADGES = [
  { key: 'freshness', label: 'Freshness', requiresFreshnessColumn: true },
  { key: 'row_count', label: 'Row Count' },
  { key: 'null_rate', label: 'Null Rate' },
  { key: 'schema_drift', label: 'Schema Drift' },
  { key: 'anomaly_detection', label: 'Anomaly Detection' },
]

const STATUS_STYLES = {
  passing: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  failing: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  unknown: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

function getMonitorStatus(table) {
  if (!table.is_active || !table.latest_profile) return 'unknown'
  return table.latest_profile.error ? 'failing' : 'passing'
}

function getChecks(table) {
  return CHECK_BADGES.filter((check) => !check.requiresFreshnessColumn || table.freshness_column)
}

function StatusBadge({ status }) {
  return (
    <Badge variant="outline" className={STATUS_STYLES[status] || STATUS_STYLES.unknown}>
      {status}
    </Badge>
  )
}

function CheckTypeBadges({ checks }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {checks.map((check) => (
        <Badge key={check.key} variant="secondary" className="font-normal">
          {check.label}
        </Badge>
      ))}
    </div>
  )
}

function getErrorMessage(err) {
  return err.response?.data?.detail || err.message || 'Failed to load monitors'
}

export default function Monitors() {
  const nav = useNavigate()
  const [tables, setTables] = useState([])
  const [sources, setSources] = useState([])
  const [status, setStatus] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([getTables(), getSources()])
      .then(([tablesResponse, sourcesResponse]) => {
        setTables(tablesResponse.data)
        setSources(sourcesResponse.data)
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false))
  }, [])

  const sourceMap = useMemo(() => Object.fromEntries(sources.map((source) => [source.id, source])), [sources])

  const monitorRows = useMemo(() => (
    tables.map((table) => {
      const checks = getChecks(table)
      return {
        ...table,
        checks,
        status: getMonitorStatus(table),
        sourceName: sourceMap[table.source_id]?.name ?? 'Unknown source',
      }
    })
  ), [sourceMap, tables])

  const filteredRows = useMemo(() => (
    monitorRows.filter((row) => status === 'all' || row.status === status)
  ), [monitorRows, status])

  const counts = useMemo(() => (
    monitorRows.reduce((acc, row) => {
      acc[row.status] = (acc[row.status] || 0) + 1
      return acc
    }, { passing: 0, failing: 0, unknown: 0 })
  ), [monitorRows])

  if (loading) return <LoadingState label="Loading monitors" />

  return (
    <div className="dw-page">
      <PageHeader
        title="Monitors"
        description={`${filteredRows.length} of ${monitorRows.length} monitor sets`}
        actions={
          <>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-full sm:w-44">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="passing">Passing</SelectItem>
                  <SelectItem value="failing">Failing</SelectItem>
                  <SelectItem value="unknown">Unknown</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <Button type="button" onClick={() => toast.info('Custom monitors coming soon')}>
              <Plus data-icon="inline-start" />
              Add monitor
            </Button>
          </>
        }
      />

      {error && (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="p-4 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <div className="text-sm text-muted-foreground">Passing</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-foreground">{counts.passing}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-sm text-muted-foreground">Failing</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-foreground">{counts.failing}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-sm text-muted-foreground">Unknown</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-foreground">{counts.unknown}</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="pt-6">
          {monitorRows.length === 0 && !error ? (
            <EmptyState
              icon={Activity}
              title="No monitors configured"
              description="Add monitored tables in Settings to start collecting profiles and check results."
              action={
                <Button type="button" onClick={() => nav('/settings')}>
                  <Plus data-icon="inline-start" />
                  Open settings
                </Button>
              }
            />
          ) : (
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Table</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Check types</TableHead>
                    <TableHead className="w-24">Checks</TableHead>
                    <TableHead>Last run</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredRows.map((row) => (
                    <TableRow key={row.id} className="cursor-pointer" onClick={() => nav(`/tables/${row.id}`)}>
                      <TableCell>
                        <div className="font-mono text-xs">{row.schema_name}.{row.table_name}</div>
                        <div className="mt-1 text-xs text-muted-foreground">Every {row.check_interval_minutes}m</div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{row.sourceName}</TableCell>
                      <TableCell><CheckTypeBadges checks={row.checks} /></TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">{row.checks.length}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDateTime(row.last_profiled_at || row.latest_profile?.collected_at)}</TableCell>
                      <TableCell><StatusBadge status={row.status} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {filteredRows.length === 0 && (
                <div className="border-t px-4 py-8 text-center text-sm text-muted-foreground">No monitors match the current filters.</div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
