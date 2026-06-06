import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Database, Loader2, RefreshCw, Search, Sparkles, Table2 } from 'lucide-react'
import { createTable, discoverSource, getSchemas, getSourceTableSchema, recommendMonitors } from '@/api/endpoints'
import { notify } from '@/lib/notify'
import { extractColumnsFromDDL, freshnessCandidates } from '@/lib/connectorConfig'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

const INTERVALS = [
  { value: '15', label: 'Every 15 minutes' },
  { value: '30', label: 'Every 30 minutes' },
  { value: '60', label: 'Hourly' },
  { value: '360', label: 'Every 6 hours' },
  { value: '1440', label: 'Daily' },
]

const SENSITIVITY = [
  { value: '2.0', label: 'High sensitivity' },
  { value: '3.0', label: 'Balanced' },
  { value: '4.0', label: 'Conservative' },
]

function flattenSchemas(schemas) {
  return schemas.flatMap((schema) =>
    schema.tables.map((table) => ({
      schema_name: schema.name,
      table_name: table.name,
      estimated_rows: table.estimated_rows,
    }))
  )
}

export default function TableSetupDialog({ open, onOpenChange, sources, onCreated }) {
  const [sourceId, setSourceId] = useState('')
  const [schemas, setSchemas] = useState([])
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')
  const [manual, setManual] = useState(false)
  const [manualTable, setManualTable] = useState({ schema_name: 'public', table_name: '' })
  const [ddl, setDdl] = useState('')
  const [freshnessColumn, setFreshnessColumn] = useState('none')
  const [interval, setInterval] = useState('60')
  const [sensitivity, setSensitivity] = useState('3.0')
  const [loadingSchemas, setLoadingSchemas] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [loadingDdl, setLoadingDdl] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [step, setStep] = useState('setup') // 'setup' | 'recommendations'
  const [recs, setRecs] = useState(null)
  const [recsLoading, setRecsLoading] = useState(false)
  const [applying, setApplying] = useState({})
  const [applied, setApplied] = useState({})
  const [createdTable, setCreatedTable] = useState(null)

  useEffect(() => {
    if (!open) return
    setStep('setup')
    setRecs(null)
    setApplying({})
    setApplied({})
    setCreatedTable(null)
    const firstConnected = sources.find((source) => source.status === 'connected') || sources[0]
    if (firstConnected) {
      setSourceId(String(firstConnected.id))
    }
  }, [open, sources])

  useEffect(() => {
    if (!open || !sourceId) return
    loadSchemas(false)
  }, [open, sourceId])

  const currentSource = sources.find((source) => String(source.id) === String(sourceId))
  const discoveredTables = useMemo(() => flattenSchemas(schemas), [schemas])
  const filteredTables = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return discoveredTables
    return discoveredTables.filter((table) => `${table.schema_name}.${table.table_name}`.toLowerCase().includes(needle))
  }, [discoveredTables, query])
  const columns = useMemo(() => extractColumnsFromDDL(ddl), [ddl])
  const candidateColumns = useMemo(() => freshnessCandidates(columns), [columns])

  async function loadSchemas(forceRefresh = false) {
    if (!sourceId) return
    setError('')
    setSelected(null)
    setDdl('')
    setFreshnessColumn('none')
    if (forceRefresh) setRefreshing(true)
    else setLoadingSchemas(true)
    try {
      const response = forceRefresh ? await discoverSource(sourceId) : await getSchemas(sourceId)
      setSchemas(response.data.schemas || [])
      if (forceRefresh) notify.source.discovered(currentSource?.name || 'Source', response.data.schemas?.length || 0)
    } catch (err) {
      const message = err.response?.data?.detail || 'Schema discovery failed'
      setSchemas([])
      setError(message)
    } finally {
      setLoadingSchemas(false)
      setRefreshing(false)
    }
  }

  async function chooseTable(table) {
    setSelected(table)
    setManual(false)
    setDdl('')
    setFreshnessColumn('none')
    setLoadingDdl(true)
    try {
      const response = await getSourceTableSchema(sourceId, {
        schema_name: table.schema_name,
        table_name: table.table_name,
      })
      setDdl(response.data.ddl || '')
      const candidates = freshnessCandidates(extractColumnsFromDDL(response.data.ddl || ''))
      if (candidates[0]) setFreshnessColumn(candidates[0].name)
    } catch (_) {
      setDdl('')
    } finally {
      setLoadingDdl(false)
    }
  }

  async function submit(event) {
    event.preventDefault()
    const table = manual ? manualTable : selected
    if (!table?.schema_name || !table?.table_name) {
      setError('Select a discovered table or enter a manual schema and table.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const response = await createTable({
        source_id: sourceId,
        schema_name: table.schema_name,
        table_name: table.table_name,
        freshness_column: freshnessColumn === 'none' ? null : freshnessColumn,
        check_interval_minutes: Number(interval),
        sensitivity: Number(sensitivity),
        dbt_model_yaml: ddl || null,
      })
      onCreated(response.data)
      setCreatedTable({ ...table, id: response.data.id })
      notify.table.added(`${table.schema_name}.${table.table_name}`)
      // Transition to recommendations step
      setStep('recommendations')
      setRecsLoading(true)
      try {
        const recResponse = await recommendMonitors(sourceId, {
          source_id: sourceId,
          table_name: table.table_name,
          schema_name: table.schema_name,
        })
        setRecs(recResponse.data.recommendations || [])
      } catch {
        setRecs([])
      } finally {
        setRecsLoading(false)
      }
    } catch (err) {
      const message = err.response?.data?.detail || 'Failed to add table'
      setError(message)
      notify.err(message)
    } finally {
      setSaving(false)
    }
  }

  const SEVERITY_COLORS = { P1: 'text-red-600 dark:text-red-400', P2: 'text-orange-600 dark:text-orange-400', P3: 'text-yellow-600 dark:text-yellow-400' }

  async function applyRec(rec, index) {
    setApplying((prev) => ({ ...prev, [index]: true }))
    try {
      await createTable({
        source_id: sourceId,
        schema_name: createdTable?.schema_name || '',
        table_name: createdTable?.table_name || '',
        freshness_column: rec.column_name || null,
        check_interval_minutes: Number(interval),
        sensitivity: Number(sensitivity),
      })
      setApplied((prev) => ({ ...prev, [index]: true }))
      notify.ok('Monitor added', rec.name)
    } catch (e) {
      notify.err(e?.response?.data?.detail || 'Failed to add monitor')
    } finally {
      setApplying((prev) => { const next = { ...prev }; delete next[index]; return next })
    }
  }

  if (step === 'recommendations') {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[92vh] overflow-hidden p-0 sm:max-w-2xl">
          <div className="flex max-h-[92vh] flex-col">
            <DialogHeader className="border-b px-5 py-4">
              <DialogTitle className="flex items-center gap-2">
                <Sparkles className="size-4 text-primary" />
                Recommended monitors
              </DialogTitle>
              <DialogDescription>
                Table <span className="font-mono text-foreground">{createdTable?.schema_name}.{createdTable?.table_name}</span> added. Apply suggested monitors with one click.
              </DialogDescription>
            </DialogHeader>
            <div className="min-h-0 flex-1 overflow-y-auto p-5">
              {recsLoading ? (
                <div className="flex flex-col gap-2">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-16 animate-pulse rounded-lg border bg-muted/40" />
                  ))}
                </div>
              ) : recs?.length === 0 ? (
                <p className="text-sm text-muted-foreground">No monitor recommendations generated for this table.</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {recs?.map((r, i) => (
                    <div key={i} className="rounded-lg border bg-muted/20 px-3 py-2.5 flex flex-col gap-1.5">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold ${SEVERITY_COLORS[r.severity] || ''}`}>{r.severity}</span>
                        <span className="text-sm font-medium">{r.name}</span>
                        <span className="rounded-full border px-2 py-0.5 text-xs font-mono">{r.monitor_type}</span>
                        <div className="ml-auto">
                          {applied[i] ? (
                            <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                              <CheckCircle2 className="size-3.5" /> Added
                            </span>
                          ) : (
                            <Button size="sm" variant="outline" disabled={applying[i]} onClick={() => applyRec(r, i)}>
                              {applying[i] ? <Loader2 className="size-3.5 animate-spin" /> : 'Add monitor'}
                            </Button>
                          )}
                        </div>
                      </div>
                      {r.rationale && <p className="text-xs text-muted-foreground">{r.rationale}</p>}
                      {r.column_name && <p className="text-xs text-muted-foreground">Column: <code className="text-primary">{r.column_name}</code></p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <DialogFooter className="border-t px-5 py-3">
              <Button type="button" onClick={() => onOpenChange(false)}>Done</Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-hidden p-0 sm:max-w-5xl">
        <form onSubmit={submit} className="flex max-h-[92vh] flex-col">
          <DialogHeader className="border-b px-5 py-4">
            <DialogTitle>Add monitored table</DialogTitle>
            <DialogDescription>Discover tables from a tested source, select the object, then choose profiling options.</DialogDescription>
          </DialogHeader>

          <div className="grid min-h-0 flex-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="min-h-0 overflow-y-auto p-5">
              <div className="mb-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                <div className="flex flex-col gap-2">
                  <Label>Source</Label>
                  <Select value={String(sourceId)} onValueChange={(value) => setSourceId(value)}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select source" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {sources.map((source) => (
                          <SelectItem key={source.id} value={String(source.id)}>
                            {source.name} · {source.type}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-end gap-2">
                  <Button type="button" variant="outline" onClick={() => loadSchemas(true)} disabled={!sourceId || refreshing}>
                    <RefreshCw data-icon="inline-start" className={refreshing ? 'animate-spin' : ''} />
                    Refresh schema
                  </Button>
                </div>
              </div>

              <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="relative sm:w-80">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input className="pl-8" placeholder="Search discovered tables" value={query} onChange={(event) => setQuery(event.target.value)} />
                </div>
                <Button type="button" variant="ghost" onClick={() => { setManual((prev) => !prev); setSelected(null) }}>
                  {manual ? 'Use discovered table' : 'Manual fallback'}
                </Button>
              </div>

              {manual ? (
                <div className="grid gap-3 rounded-md border bg-muted/20 p-3 sm:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="manual-schema">Schema</Label>
                    <Input id="manual-schema" value={manualTable.schema_name} onChange={(event) => setManualTable((prev) => ({ ...prev, schema_name: event.target.value }))} />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="manual-table">Table</Label>
                    <Input id="manual-table" value={manualTable.table_name} onChange={(event) => setManualTable((prev) => ({ ...prev, table_name: event.target.value }))} />
                  </div>
                </div>
              ) : loadingSchemas ? (
                <div className="flex items-center gap-2 rounded-md border p-6 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Loading schema inventory
                </div>
              ) : filteredTables.length === 0 ? (
                <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
                  No discovered tables. Refresh schema or use manual fallback.
                </div>
              ) : (
                <div className="max-h-[390px] overflow-y-auto rounded-md border">
                  {filteredTables.map((table) => {
                    const active = selected?.schema_name === table.schema_name && selected?.table_name === table.table_name
                    return (
                      <button
                        type="button"
                        key={`${table.schema_name}.${table.table_name}`}
                        className={cn(
                          'flex w-full items-center justify-between gap-3 border-b px-3 py-2 text-left text-sm last:border-b-0 hover:bg-muted/50',
                          active && 'bg-primary/10 text-primary'
                        )}
                        onClick={() => chooseTable(table)}
                      >
                        <span className="min-w-0">
                          <span className="font-mono text-xs">{table.schema_name}.{table.table_name}</span>
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {table.estimated_rows == null ? 'rows unknown' : `${Number(table.estimated_rows).toLocaleString()} rows`}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}

              {error && (
                <Alert variant="destructive" className="mt-4">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
            </div>

            <aside className="min-h-0 overflow-y-auto border-t bg-muted/20 p-5 lg:border-l lg:border-t-0">
              <div className="mb-4 flex items-center gap-2 text-sm font-medium">
                {manual ? <Table2 className="size-4" /> : <Database className="size-4" />}
                {manual ? 'Manual table' : selected ? `${selected.schema_name}.${selected.table_name}` : 'Table setup'}
              </div>

              <div className="space-y-4">
                <div className="flex flex-col gap-2">
                  <Label>Freshness column</Label>
                  <Select value={freshnessColumn} onValueChange={setFreshnessColumn}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectItem value="none">No freshness check</SelectItem>
                        {candidateColumns.map((column) => (
                          <SelectItem key={column.name} value={column.name}>{column.name}</SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                  <div className="flex flex-col gap-2">
                    <Label>Profiling cadence</Label>
                    <Select value={interval} onValueChange={setInterval}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          {INTERVALS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                          ))}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label>Anomaly sensitivity</Label>
                    <Select value={sensitivity} onValueChange={setSensitivity}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          {SENSITIVITY.map((option) => (
                            <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                          ))}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="flex flex-col gap-2">
                  <Label>Schema snapshot</Label>
                  {loadingDdl ? (
                    <div className="flex items-center gap-2 rounded-md border bg-card p-3 text-xs text-muted-foreground">
                      <Loader2 className="size-3.5 animate-spin" />
                      Loading DDL
                    </div>
                  ) : (
                    <Textarea
                      className="min-h-44 font-mono text-xs"
                      value={ddl}
                      onChange={(event) => setDdl(event.target.value)}
                      placeholder="DDL will appear after selecting a discovered table."
                    />
                  )}
                </div>
              </div>
            </aside>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={saving || !sourceId || (!manual && !selected) || (manual && !manualTable.table_name.trim())}>
              {saving ? 'Adding...' : 'Start monitoring'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

