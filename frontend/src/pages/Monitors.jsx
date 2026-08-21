import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, Code2, Database, FileCode2, Loader2, Play, RefreshCw, ShieldCheck, Table2 } from 'lucide-react'
import {
  getAllCustomMonitors,
  getSafeMonitorRuns,
  getSafeMonitors,
  getTables,
  runSafeMonitorNow,
} from '../api/endpoints'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, formatDateTime } from '../components/app-ui'
import { notify } from '@/lib/notify'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const FILTERS = [
  { value: 'all', label: 'All monitors' },
  { value: 'dsl', label: 'Typed DSL' },
  { value: 'legacy', label: 'Legacy SQL' },
]

const DSL_STATUS_STYLES = {
  active: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  draft: 'border-amber-600/25 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  paused: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

const RUN_STATUS_STYLES = {
  succeeded: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  failed: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  queued: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
  running: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

function tableLabel(table) {
  return table ? `${table.schema_name}.${table.table_name}` : 'Unknown table'
}

function statusLabel(value) {
  return String(value || 'unknown').replaceAll('_', ' ')
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

function MonitorCard({ monitor, onOpenTable, onRun, running }) {
  const isDsl = monitor.kind === 'dsl'
  const tableId = monitor.tableId || monitor.table_id
  const latest = monitor.latestRun
  const monitorStatus = isDsl ? monitor.status : monitor.is_active ? 'active' : 'paused'
  const runStatus = latest?.status || (isDsl && monitorStatus === 'active' ? 'not_run' : null)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="gap-3 border-b bg-muted/20 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border bg-background text-muted-foreground">
              {isDsl ? <ShieldCheck className="size-4" /> : <Code2 className="size-4" />}
            </div>
            <div className="min-w-0">
              <CardTitle className="truncate text-base">{monitor.name}</CardTitle>
              <button type="button" className="mt-1 flex items-center gap-1 text-left text-xs text-muted-foreground hover:text-foreground" onClick={() => onOpenTable(tableId)}>
                <Table2 className="size-3" />
                <span className="truncate">{monitor.tableLabel}</span>
              </button>
            </div>
          </div>
          <Badge variant="outline" className="shrink-0">{isDsl ? 'Typed DSL' : 'Legacy SQL'}</Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pt-4">
        {isDsl ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className={DSL_STATUS_STYLES[monitorStatus] || ''}>{statusLabel(monitorStatus)}</Badge>
              <Badge variant="outline">Revision {monitor.currentRevision}</Badge>
              {runStatus && <Badge variant="outline" className={RUN_STATUS_STYLES[runStatus] || ''}>{statusLabel(runStatus)}</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">
              {latest
                ? `${latest.result?.transition || latest.errorCode || 'completed'} · ${formatDateTime(latest.completedAt || latest.queuedAt)}`
                : monitorStatus === 'active'
                  ? 'Waiting for the first profile or a manual run.'
                  : 'Draft revision. Preview and activate it before execution.'}
            </p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{monitor.definitionVersion || 'datawatch.io/v1alpha1'}</span>
              {monitor.activationSupported === false && <span>· activation gated by connector capability</span>}
            </div>
            <div className="flex flex-wrap gap-2">
              {monitorStatus === 'active' && (
                <Button size="sm" variant="outline" onClick={() => onRun(monitor)} disabled={running}>
                  {running ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                  {running ? 'Queueing…' : 'Run now'}
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => onOpenTable(tableId)}>Open table</Button>
            </div>
          </>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className={DSL_STATUS_STYLES[monitorStatus] || ''}>{monitorStatus}</Badge>
              <Badge variant="outline">{monitor.severity}</Badge>
              {monitor.run_on_profile && <span className="text-xs text-muted-foreground">Runs on every profile</span>}
            </div>
            <p className="line-clamp-2 text-sm text-muted-foreground">{monitor.description || 'SQL violation check managed from the table detail page.'}</p>
            <p className="text-xs text-muted-foreground">Last run: {formatDateTime(monitor.last_run_at)}</p>
            <Button size="sm" variant="ghost" className="w-fit" onClick={() => onOpenTable(monitor.table_id)}>Open table</Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}

export default function Monitors() {
  const nav = useNavigate()
  const [tables, setTables] = useState([])
  const [monitors, setMonitors] = useState([])
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [running, setRunning] = useState({})

  const load = async ({ quiet = false } = {}) => {
    if (quiet) setRefreshing(true)
    else setLoading(true)
    setError('')
    try {
      const [tablesResponse, legacyResponse] = await Promise.all([getTables(), getAllCustomMonitors()])
      const nextTables = tablesResponse.data || []
      const tableById = Object.fromEntries(nextTables.map((table) => [table.id, table]))
      const dslResults = await Promise.allSettled(nextTables.map((table) => getSafeMonitors(table.id)))
      const dslMonitors = []
      let dslFailures = 0
      dslResults.forEach((result, index) => {
        if (result.status === 'rejected') {
          dslFailures += 1
          return
        }
        for (const monitor of result.value.data || []) {
          const tableId = monitor.assetId || nextTables[index].id
          dslMonitors.push({
            ...monitor,
            kind: 'dsl',
            tableId,
            tableLabel: tableLabel(tableById[tableId]),
          })
        }
      })

      const runResults = await Promise.allSettled(
        dslMonitors.map((monitor) => getSafeMonitorRuns(monitor.id)),
      )
      runResults.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          dslMonitors[index].latestRun = (result.value.data || [])[0] || null
        }
      })

      const legacyMonitors = (legacyResponse.data || []).map((monitor) => ({
        ...monitor,
        kind: 'legacy',
        tableLabel: tableLabel(tableById[monitor.table_id]),
      }))
      setTables(nextTables)
      setMonitors([...dslMonitors, ...legacyMonitors])
      if (dslFailures && dslFailures === nextTables.length) {
        setError('Typed DSL monitor data is temporarily unavailable. Legacy SQL monitors are still shown.')
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load monitors')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const visibleMonitors = useMemo(
    () => monitors.filter((monitor) => filter === 'all' || monitor.kind === filter),
    [filter, monitors],
  )
  const dslCount = monitors.filter((monitor) => monitor.kind === 'dsl').length
  const activeDslCount = monitors.filter((monitor) => monitor.kind === 'dsl' && monitor.status === 'active').length
  const legacyCount = monitors.filter((monitor) => monitor.kind === 'legacy').length

  const openTable = (tableId) => nav(`/tables/${tableId}`)

  const runMonitor = async (monitor) => {
    setRunning((current) => ({ ...current, [monitor.id]: true }))
    try {
      await runSafeMonitorNow(monitor.id, `monitors-page-${monitor.id}-${Date.now()}`)
      notify.ok('Typed DSL monitor queued', monitor.name)
      await load({ quiet: true })
    } catch (err) {
      notify.err(err?.response?.data?.detail?.message || err?.response?.data?.detail || 'Unable to queue typed DSL monitor')
    } finally {
      setRunning((current) => ({ ...current, [monitor.id]: false }))
    }
  }

  if (loading && monitors.length === 0) return <LoadingState label="Loading monitors" />

  return (
    <div className="dw-page">
      <PageHeader
        title="Monitors"
        description="Typed DSL monitors and legacy SQL checks across every monitored table."
        actions={(
          <Button variant="outline" size="sm" onClick={() => load({ quiet: true })} disabled={refreshing}>
            {refreshing ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
            Refresh
          </Button>
        )}
      />

      <ErrorNotice message={error} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryItem icon={ShieldCheck} label="Typed DSL" value={dslCount} detail={`${activeDslCount} active`} />
        <SummaryItem icon={Activity} label="Active runtime" value={activeDslCount} detail="Schema-bound monitors" />
        <SummaryItem icon={Code2} label="Legacy SQL" value={legacyCount} detail="Custom table checks" />
        <SummaryItem icon={Database} label="Tables covered" value={tables.length} detail="Available monitor targets" />
      </div>

      <Card className="border-dashed bg-muted/20">
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <FileCode2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">Typed DSL runtime</p>
              <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                DSL monitors are schema-bound, revisioned, and run safely on supported connectors. Create or preview their definitions through the v1alpha1 monitor API; this page is the workspace inventory and run control surface.
              </p>
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={() => nav('/help')}>Read DSL guide</Button>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2 border-b pb-3">
        {FILTERS.map((item) => (
          <Button key={item.value} type="button" size="sm" variant={filter === item.value ? 'secondary' : 'ghost'} onClick={() => setFilter(item.value)}>
            {item.label}
          </Button>
        ))}
        <span className="ml-auto text-xs text-muted-foreground">{visibleMonitors.length} shown</span>
      </div>

      {visibleMonitors.length === 0 ? (
        <EmptyState
          icon={filter === 'dsl' ? ShieldCheck : Code2}
          title={filter === 'dsl' ? 'No typed DSL monitors yet' : filter === 'legacy' ? 'No legacy SQL monitors' : 'No monitors yet'}
          description={filter === 'dsl'
            ? 'Use the v1alpha1 monitor API to validate and create a schema-bound definition. Once active, it will appear here and on its table detail page.'
            : 'Create a monitor from a table detail page to start checking data quality.'}
          action={filter === 'dsl' ? <Button variant="outline" onClick={() => nav('/help')}>Open DSL guide</Button> : <Button onClick={() => nav('/tables')}>Open tables</Button>}
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {visibleMonitors.map((monitor) => (
            <MonitorCard
              key={`${monitor.kind}-${monitor.id}`}
              monitor={monitor}
              onOpenTable={openTable}
              onRun={runMonitor}
              running={!!running[monitor.id]}
            />
          ))}
        </div>
      )}
    </div>
  )
}
