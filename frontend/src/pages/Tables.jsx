import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, Plus, Search, Table2 } from 'lucide-react'
import { getSources, getTables, runTable } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, formatDateTime, formatNumber } from '../components/app-ui'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

export default function Tables() {
  const nav = useNavigate()
  const [tables, setTables] = useState([])
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [running, setRunning] = useState({})
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')

  useEffect(() => {
    Promise.all([getTables(), getSources()])
      .then(([tablesResponse, sourcesResponse]) => {
        setTables(tablesResponse.data)
        setSources(sourcesResponse.data)
      })
      .catch((err) => setError(err.response?.data?.detail || 'Failed to load tables'))
      .finally(() => setLoading(false))
  }, [])

  const sourceMap = Object.fromEntries(sources.map((source) => [source.id, source]))

  const filteredTables = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return tables.filter((table) => {
      const tableStatus = table.latest_profile?.error ? 'error' : table.is_active ? 'healthy' : 'paused'
      const matchesStatus = status === 'all' || status === tableStatus
      const label = `${table.schema_name}.${table.table_name} ${sourceMap[table.source_id]?.name || ''}`.toLowerCase()
      return matchesStatus && (!needle || label.includes(needle))
    })
  }, [query, sourceMap, status, tables])

  const handleRun = async (e, id) => {
    e.stopPropagation()
    setRunning((prev) => ({ ...prev, [id]: true }))
    try {
      await runTable(id)
    } catch (_) {
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

  if (loading) return <LoadingState label="Loading monitored tables" />

  return (
    <div className="dw-page">
      <PageHeader
        title="Tables"
        description={`${filteredTables.length} of ${tables.length} monitored tables`}
        actions={
          <Button type="button" onClick={() => nav('/settings')}>
            <Plus data-icon="inline-start" />
            Add table
          </Button>
        }
      />

      <ErrorNotice message={error} />

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative sm:w-80">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-8" placeholder="Search tables or sources" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
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

          {tables.length === 0 && !error ? (
            <EmptyState
              icon={Table2}
              title="No tables monitored"
              description="Add a data source and configure the first monitored table in Settings."
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
                    <TableHead>Rows</TableHead>
                    <TableHead>Last profile</TableHead>
                    <TableHead>Interval</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-24 text-right">Action</TableHead>
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
                        <HealthBadge status={table.latest_profile?.error ? 'error' : table.is_active ? 'healthy' : 'paused'} />
                      </TableCell>
                      <TableCell className="text-right">
                        <Button type="button" variant="outline" size="sm" onClick={(e) => handleRun(e, table.id)} disabled={!!running[table.id]}>
                          <Play data-icon="inline-start" />
                          {running[table.id] ? 'Queued' : 'Run'}
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
          )}
        </CardContent>
      </Card>
    </div>
  )
}
