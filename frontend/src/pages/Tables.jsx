import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, Plus, RefreshCw, Search, Table2, Trash2 } from 'lucide-react'
import { deleteTable, getSources, getTables, runTable } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import TableSetupDialog from '../components/TableSetupDialog'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, formatDateTime, formatNumber } from '../components/app-ui'
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

const getTableStatus = (table) => (table.latest_profile?.error ? 'error' : table.is_active ? 'healthy' : 'paused')

export default function Tables() {
  const nav = useNavigate()
  const [tables, setTables] = useState([])
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [running, setRunning] = useState({})
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [pendingDelete, setPendingDelete] = useState(null)

  const load = async (isRefresh = false) => {
    setError('')
    if (isRefresh) setRefreshing(true)
    try {
      const [tablesResponse, sourcesResponse] = await Promise.all([getTables(), getSources()])
      setTables(tablesResponse.data)
      setSources(sourcesResponse.data)
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

  const filteredTables = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return tables.filter((table) => {
      const matchesStatus = status === 'all' || status === getTableStatus(table)
      const matchesSource = sourceFilter === 'all' || String(table.source_id) === sourceFilter
      const label = `${table.schema_name}.${table.table_name} ${sourceMap[table.source_id]?.name || ''}`.toLowerCase()
      return matchesStatus && matchesSource && (!needle || label.includes(needle))
    })
  }, [query, sourceFilter, sourceMap, status, tables])

  const handleRun = async (e, id) => {
    e.stopPropagation()
    setRunning((prev) => ({ ...prev, [id]: true }))
    try {
      await runTable(id)
      const table = tables.find((item) => item.id === id)
      notify.table.runQueued(table ? `${table.schema_name}.${table.table_name}` : 'table')
    } catch (_) {
      notify.err('Failed to queue profile run')
    } finally {
      setTimeout(() => {
        setRunning((prev) => {
          const next = { ...prev }
          delete next[id]
          return next
        })
      }, 2000)
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

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div className="relative sm:w-80">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-8" placeholder="Search tables or sources" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
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
                    <SelectItem value="paused">Paused</SelectItem>
                    <SelectItem value="error">Error</SelectItem>
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
                  role="button"
                  tabIndex={0}
                  className="w-full cursor-pointer rounded-md border bg-background p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => nav(`/tables/${table.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      nav(`/tables/${table.id}`)
                    }
                  }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-mono text-xs font-semibold">{table.schema_name}.{table.table_name}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{sourceMap[table.source_id]?.name ?? '—'}</div>
                    </div>
                    <HealthBadge status={getTableStatus(table)} />
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <div className="text-muted-foreground">Rows</div>
                      <div className="mt-1 tabular-nums">{formatNumber(table.latest_profile?.row_count)}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Profile</div>
                      <div className="mt-1">{formatDateTime(table.last_profiled_at)}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Interval</div>
                      <div className="mt-1">{table.check_interval_minutes}m</div>
                    </div>
                  </div>
                  <div className="mt-3 flex justify-end gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={(e) => handleRun(e, table.id)} disabled={!!running[table.id]}>
                      <Play data-icon="inline-start" />
                      {running[table.id] ? 'Queued' : 'Run'}
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
                    <TableHead>Interval</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-40 text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredTables.map((table) => (
                    <TableRow key={table.id} className="cursor-pointer" onClick={() => nav(`/tables/${table.id}`)}>
                      <TableCell className="font-mono text-xs">{table.schema_name}.{table.table_name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{sourceMap[table.source_id]?.name ?? '—'}</TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">{formatNumber(table.latest_profile?.row_count)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDateTime(table.last_profiled_at)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{table.check_interval_minutes}m</TableCell>
                      <TableCell>
                        <HealthBadge status={getTableStatus(table)} />
                      </TableCell>
                      <TableCell className="flex justify-end gap-1 text-right">
                        <Button type="button" variant="outline" size="sm" onClick={(e) => handleRun(e, table.id)} disabled={!!running[table.id]}>
                          <Play data-icon="inline-start" />
                          {running[table.id] ? 'Queued' : 'Run'}
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
