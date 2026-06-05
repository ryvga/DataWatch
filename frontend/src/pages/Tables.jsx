import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Clock, Database, Loader2, Play, Plus, RefreshCw, Search, Table2, Trash2 } from 'lucide-react'
import { deleteTable, getIncidents, getSources, getTables, runTable } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import TableSetupDialog from '../components/TableSetupDialog'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, formatDateTime } from '../components/app-ui'
import { notify } from '@/lib/notify'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const ACTIVE_INCIDENT_STATUSES = new Set(['open', 'acknowledged', 'investigating'])
const STATUS_RANK = {
  incident: 0,
  error: 1,
  'never-profiled': 2,
  paused: 3,
  healthy: 4,
}

function tableLabel(table) {
  return `${table.schema_name}.${table.table_name}`
}

function getProfiledAt(table) {
  return table.last_profiled_at || table.latest_profile?.collected_at || null
}

function getTableStatus(table, incidentCount = 0) {
  if (!table.is_active) return 'paused'
  if (!getProfiledAt(table) && !table.latest_profile) return 'never-profiled'
  if (table.latest_profile?.error) return 'error'
  if (incidentCount > 0) return 'incident'
  return 'healthy'
}

function formatCompactNumber(value) {
  if (value == null) return '-'
  return new Intl.NumberFormat('en', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(Number(value)).toLowerCase()
}

function formatTimeAgo(value) {
  if (!value) return 'Never'

  const timestamp = new Date(value).getTime()
  if (Number.isNaN(timestamp)) return 'Never'

  const diffSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (diffSeconds < 60) return 'Just now'

  const units = [
    ['y', 60 * 60 * 24 * 365],
    ['d', 60 * 60 * 24],
    ['h', 60 * 60],
    ['m', 60],
  ]
  const [label, seconds] = units.find(([, unitSeconds]) => diffSeconds >= unitSeconds)
  return `${Math.floor(diffSeconds / seconds)}${label} ago`
}

function SummaryItem({ icon: Icon, label, value, detail }) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-md border bg-card px-4 py-3">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        <Icon className="size-4" />
      </div>
      <div className="min-w-0">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="mt-0.5 truncate text-lg font-semibold tabular-nums text-foreground">{value}</div>
        {detail && <div className="truncate text-xs text-muted-foreground">{detail}</div>}
      </div>
    </div>
  )
}

export default function Tables() {
  const nav = useNavigate()
  const [tables, setTables] = useState([])
  const [sources, setSources] = useState([])
  const [incidents, setIncidents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [running, setRunning] = useState({})
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [sortBy, setSortBy] = useState('name')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [pendingDelete, setPendingDelete] = useState(null)

  const load = async (isRefresh = false) => {
    setError('')
    if (isRefresh) setRefreshing(true)
    try {
      const [tablesResponse, sourcesResponse, incidentsResponse] = await Promise.all([
        getTables(),
        getSources(),
        getIncidents({ limit: 250 }),
      ])
      setTables(tablesResponse.data)
      setSources(sourcesResponse.data)
      setIncidents(incidentsResponse.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load tables')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const sourceMap = useMemo(() => Object.fromEntries(sources.map((source) => [source.id, source])), [sources])

  const activeIncidents = useMemo(
    () => incidents.filter((incident) => ACTIVE_INCIDENT_STATUSES.has(String(incident.status).toLowerCase())),
    [incidents]
  )

  const incidentCountByTable = useMemo(() => {
    const counts = new Map()
    activeIncidents.forEach((incident) => {
      counts.set(incident.table_id, (counts.get(incident.table_id) || 0) + 1)
    })
    return counts
  }, [activeIncidents])

  const tableRows = useMemo(
    () => tables.map((table) => {
      const profiledAt = getProfiledAt(table)
      const source = sourceMap[table.source_id]
      const incidentCount = incidentCountByTable.get(table.id) || 0
      const label = tableLabel(table)

      return {
        ...table,
        label,
        sourceName: source?.name || '-',
        profiledAt,
        incidentCount,
        status: getTableStatus(table, incidentCount),
      }
    }),
    [incidentCountByTable, sourceMap, tables]
  )

  const summary = useMemo(() => {
    const lastProfiledAt = tableRows.reduce((latest, table) => {
      if (!table.profiledAt) return latest
      const value = new Date(table.profiledAt).getTime()
      if (Number.isNaN(value)) return latest
      return !latest || value > latest ? value : latest
    }, null)

    return {
      total: tableRows.length,
      healthy: tableRows.filter((table) => table.status === 'healthy').length,
      incidents: activeIncidents.length,
      lastProfiledAt,
    }
  }, [activeIncidents.length, tableRows])

  const filteredTables = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return tableRows.filter((table) => {
      const matchesStatus = status === 'all' || status === table.status
      const matchesSource = sourceFilter === 'all' || String(table.source_id) === sourceFilter
      return matchesStatus && matchesSource && (!needle || table.label.toLowerCase().includes(needle))
    }).sort((a, b) => {
      if (sortBy === 'row_count') {
        return (b.latest_profile?.row_count ?? -1) - (a.latest_profile?.row_count ?? -1)
      }
      if (sortBy === 'last_profiled') {
        return (new Date(b.profiledAt || 0).getTime() || 0) - (new Date(a.profiledAt || 0).getTime() || 0)
      }
      if (sortBy === 'status') {
        return (STATUS_RANK[a.status] ?? 99) - (STATUS_RANK[b.status] ?? 99) || a.label.localeCompare(b.label)
      }
      return a.label.localeCompare(b.label)
    })
  }, [query, sourceFilter, sortBy, status, tableRows])

  const handleRun = async (e, table) => {
    e.stopPropagation()
    const id = table.id
    setRunning((prev) => ({ ...prev, [id]: true }))
    try {
      await runTable(id)
      notify.table.runQueued(table.label || tableLabel(table))
    } catch (err) {
      notify.err(err.response?.data?.detail || 'Failed to queue profile run')
    } finally {
      setRunning((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    }
  }

  const confirmDelete = async () => {
    const table = pendingDelete
    if (!table) return
    try {
      await deleteTable(table.id)
      setTables((prev) => prev.filter((item) => item.id !== table.id))
      setPendingDelete(null)
      notify.table.removed(`${table.schema_name}.${table.table_name}`)
    } catch (err) {
      notify.err(err.response?.data?.detail || 'Failed to remove table')
    }
  }

  if (loading) return <LoadingState label="Loading monitored tables" />

  return (
    <div className="dw-page">
      <PageHeader
        title="Tables"
        description={`${filteredTables.length} of ${tables.length} monitored tables`}
        actions={
          <>
            <Button type="button" variant="outline" onClick={() => load(true)} disabled={refreshing}>
              <RefreshCw data-icon="inline-start" className={refreshing ? 'animate-spin' : ''} />
              Refresh
            </Button>
            <Button type="button" onClick={() => setDialogOpen(true)} disabled={sources.length === 0}>
              <Plus data-icon="inline-start" />
              Add table
            </Button>
          </>
        }
      />

      <ErrorNotice message={error} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryItem icon={Database} label="Total tables" value={formatCompactNumber(summary.total)} detail="Monitored objects" />
        <SummaryItem icon={CheckCircle2} label="Healthy" value={formatCompactNumber(summary.healthy)} detail="No active signal" />
        <SummaryItem icon={AlertTriangle} label="Incidents" value={formatCompactNumber(summary.incidents)} detail="Unresolved incidents" />
        <SummaryItem
          icon={Clock}
          label="Last profiled"
          value={formatTimeAgo(summary.lastProfiledAt)}
          detail={summary.lastProfiledAt ? formatDateTime(summary.lastProfiledAt) : 'No profile history'}
        />
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div className="relative sm:w-80">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-8" placeholder="Search table name" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              <Select value={sourceFilter} onValueChange={setSourceFilter}>
                <SelectTrigger className="w-full sm:w-56">
                  <SelectValue placeholder="Source" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="all">All sources</SelectItem>
                    {sources.map((source) => (
                      <SelectItem key={source.id} value={String(source.id)}>{source.name}</SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="w-full sm:w-44">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="all">All statuses</SelectItem>
                    <SelectItem value="healthy">Healthy</SelectItem>
                    <SelectItem value="incident">Incident</SelectItem>
                    <SelectItem value="error">Error</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <Select value={sortBy} onValueChange={setSortBy}>
                <SelectTrigger className="w-full sm:w-48">
                  <SelectValue placeholder="Sort by" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="name">Name</SelectItem>
                    <SelectItem value="row_count">Row count</SelectItem>
                    <SelectItem value="last_profiled">Last profiled</SelectItem>
                    <SelectItem value="status">Status</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
          </div>

          {sources.length === 0 && !error ? (
            <EmptyState
              icon={Table2}
              title="Connect a source first"
              description="Tables are selected from a tested data source schema inventory."
              action={
                <Button type="button" onClick={() => nav('/settings')}>
                  <Plus data-icon="inline-start" />
                  Add source in Settings
                </Button>
              }
            />
          ) : tables.length === 0 && !error ? (
            <EmptyState
              icon={Table2}
              title="No tables monitored"
              description="Choose a source, refresh schema discovery, and select the first table to monitor."
              action={
                <Button type="button" onClick={() => setDialogOpen(true)}>
                  <Plus data-icon="inline-start" />
                  Add table
                </Button>
              }
            />
          ) : (
            <>
            <div className="space-y-3 md:hidden">
              {filteredTables.map((table) => (
                <div
                  key={table.id}
                  className="w-full rounded-md border bg-background p-3 text-left"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <button
                        type="button"
                        className="block max-w-full truncate font-mono text-xs font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => nav(`/tables/${table.id}`)}
                      >
                        {table.label}
                      </button>
                      <div className="mt-1 text-xs text-muted-foreground">{table.sourceName}</div>
                    </div>
                    <HealthBadge status={table.status} />
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <div className="text-muted-foreground">Rows</div>
                      <div className="mt-1 tabular-nums">{formatCompactNumber(table.latest_profile?.row_count)}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Profile</div>
                      <div className="mt-1" title={table.profiledAt ? formatDateTime(table.profiledAt) : undefined}>
                        {formatTimeAgo(table.profiledAt)}
                      </div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Incidents</div>
                      <div className="mt-1 tabular-nums">{formatCompactNumber(table.incidentCount)}</div>
                    </div>
                  </div>
                  <div className="mt-3 flex justify-end gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={(e) => handleRun(e, table)} disabled={!!running[table.id]}>
                      {running[table.id] ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Play data-icon="inline-start" />}
                      Run now
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={(e) => { e.stopPropagation(); setPendingDelete(table) }}
                      aria-label={`Remove ${table.schema_name}.${table.table_name}`}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </div>
              ))}
              {filteredTables.length === 0 && (
                <div className="rounded-md border px-4 py-8 text-center text-sm text-muted-foreground">No tables match the current filters.</div>
              )}
            </div>

            <div className="dw-table-wrap hidden md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Table</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Rows</TableHead>
                    <TableHead>Last profile</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-44 text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredTables.map((table) => (
                    <TableRow key={table.id}>
                      <TableCell>
                        <button
                          type="button"
                          className="max-w-[280px] truncate font-mono text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          onClick={() => nav(`/tables/${table.id}`)}
                        >
                          {table.label}
                        </button>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{table.sourceName}</TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">{formatCompactNumber(table.latest_profile?.row_count)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground" title={table.profiledAt ? formatDateTime(table.profiledAt) : undefined}>
                        {formatTimeAgo(table.profiledAt)}
                      </TableCell>
                      <TableCell>
                        <HealthBadge status={table.status} />
                      </TableCell>
                      <TableCell className="flex justify-end gap-1 text-right">
                        <Button type="button" variant="outline" size="sm" onClick={(e) => handleRun(e, table)} disabled={!!running[table.id]}>
                          {running[table.id] ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Play data-icon="inline-start" />}
                          Run now
                        </Button>
                        <Button type="button" variant="ghost" size="icon-sm" onClick={(e) => { e.stopPropagation(); setPendingDelete(table) }} aria-label={`Remove ${table.schema_name}.${table.table_name}`}>
                          <Trash2 className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {filteredTables.length === 0 && (
                <div className="border-t px-4 py-8 text-center text-sm text-muted-foreground">No tables match the current filters.</div>
              )}
            </div>
            </>
          )}
        </CardContent>
      </Card>
      <TableSetupDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        sources={sources}
        onCreated={(table) => setTables((prev) => [...prev, table])}
      />
      <AlertDialog open={!!pendingDelete} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove monitored table?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete ? `${pendingDelete.schema_name}.${pendingDelete.table_name}` : 'This table'} will be paused for monitoring. Historical profiles and incidents are preserved.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>Remove table</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
