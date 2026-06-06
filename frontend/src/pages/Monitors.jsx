import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, CheckCircle2, Loader2, Play, Plus, ShieldCheck, Sparkles, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { getSources, getTables, getAllCustomMonitors, createCustomMonitor, runCustomMonitorNow, deleteCustomMonitor, runCustomCheck } from '../api/endpoints'
import { EmptyState, LoadingState, PageHeader, formatDateTime } from '../components/app-ui'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
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
  const detail = err.response?.data?.detail
  if (detail?.error === 'plan_limit_exceeded') {
    return `Your ${detail.plan || 'current'} plan has reached its table or source limit. Upgrade to add more monitored assets.`
  }
  if (detail?.error === 'feature_not_in_plan') {
    return `${detail.feature || 'This feature'} requires the ${detail.required_plan || 'higher'} plan. Current plan: ${detail.current_plan || 'unknown'}.`
  }
  return (typeof detail === 'string' ? detail : null) || err.message || 'Failed to load monitors'
}

const SEVERITY_BADGE_CLASSES = {
  P1: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  P2: 'border-orange-600/25 bg-orange-600/10 text-orange-700 dark:text-orange-300',
  P3: 'border-yellow-600/25 bg-yellow-600/10 text-yellow-700 dark:text-yellow-300',
}

function CustomMonitorDialog({ open, onClose, sources, tables, onCreated }) {
  const [selectedSourceId, setSelectedSourceId] = useState('')
  const [selectedTableId, setSelectedTableId] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [sql, setSql] = useState('')
  const [severity, setSeverity] = useState('P3')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [lastTestedSql, setLastTestedSql] = useState('')

  const filteredTables = useMemo(
    () => selectedSourceId ? tables.filter((t) => t.source_id === selectedSourceId) : tables,
    [selectedSourceId, tables]
  )

  const reset = () => {
    setSelectedSourceId(''); setSelectedTableId(''); setName(''); setDescription(''); setSql(''); setSeverity('P3')
    setTesting(false); setTestResult(null); setLastTestedSql('')
  }

  const handleClose = () => { reset(); onClose() }

  const handleSqlChange = (value) => {
    setSql(value)
    setTestResult(null)
    setLastTestedSql('')
  }

  const handleTableChange = (value) => {
    setSelectedTableId(value)
    setTestResult(null)
    setLastTestedSql('')
  }

  const handleSourceChange = (value) => {
    setSelectedSourceId(value)
    setSelectedTableId('')
    setTestResult(null)
    setLastTestedSql('')
  }

  const sqlTested = selectedTableId && sql.trim() && lastTestedSql === sql.trim() && testResult

  const handleTest = async () => {
    if (!selectedTableId || !sql.trim()) return
    setTesting(true)
    setTestResult(null)
    try {
      const r = await runCustomCheck(selectedTableId, {
        sql: sql.trim(),
        name: name.trim() || 'Custom SQL monitor',
        severity,
      })
      setTestResult(r.data)
      setLastTestedSql(sql.trim())
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Test run failed')
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    if (!selectedTableId || !name.trim() || !sql.trim() || !sqlTested) return
    setSaving(true)
    try {
      await createCustomMonitor(selectedTableId, {
        name: name.trim(),
        description: description.trim() || undefined,
        sql_query: sql.trim(),
        severity,
        run_on_profile: true,
      })
      toast.success('Custom monitor created')
      reset()
      onCreated()
      onClose()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to create monitor')
    } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose() }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Custom SQL Monitor</DialogTitle>
          <DialogDescription>Create a SQL check that counts violations across a specific table.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3 py-2">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Source</label>
            <select
              className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
              value={selectedSourceId}
              onChange={e => handleSourceChange(e.target.value)}
            >
              <option value="">All sources</option>
              {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Table *</label>
            <select
              className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
              value={selectedTableId}
              onChange={e => handleTableChange(e.target.value)}
            >
              <option value="">Select a table…</option>
              {filteredTables.map((t) => (
                <option key={t.id} value={t.id}>{t.schema_name}.{t.table_name}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Name *</label>
            <input
              className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
              value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. Paid orders without reference"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Description (optional)</label>
            <input
              className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
              value={description} onChange={e => setDescription(e.target.value)}
              placeholder="What does this check detect?"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">SQL query * (returns violation count)</label>
            <textarea
              className="rounded-md border bg-background px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-primary min-h-[80px] resize-y"
              value={sql} onChange={e => handleSqlChange(e.target.value)}
              placeholder="SELECT COUNT(*) FROM orders WHERE status = 'paid' AND payment_reference IS NULL"
            />
          </div>
          {testResult && (
            <span className={`text-sm font-medium flex items-center gap-1 ${testResult.passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-orange-600 dark:text-orange-400'}`}>
              {testResult.passed
                ? <><CheckCircle2 className="size-4" /> 0 violations</>
                : <><AlertTriangle className="size-4" /> {testResult.violation_count} violation{testResult.violation_count !== 1 ? 's' : ''} found</>
              }
            </span>
          )}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Severity</label>
            <select
              className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
              value={severity} onChange={e => setSeverity(e.target.value)}
            >
              <option value="P1">P1 — Critical</option>
              <option value="P2">P2 — High</option>
              <option value="P3">P3 — Medium</option>
            </select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={handleClose}>Cancel</Button>
          <Button variant="outline" onClick={handleTest} disabled={testing || !selectedTableId || !sql.trim()}>
            {testing ? <><Loader2 className="size-3.5 animate-spin mr-1" />Testing…</> : 'Test SQL'}
          </Button>
          <Button onClick={handleSave} disabled={saving || !selectedTableId || !name.trim() || !sql.trim() || !sqlTested}>
            {saving ? <><Loader2 className="size-3.5 animate-spin mr-1" />Saving…</> : 'Create monitor'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CustomMonitorsTable({ tables, refreshKey }) {
  const [monitors, setMonitors] = useState([])
  const [loading, setLoading] = useState(true)
  const [runningId, setRunningId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const nav = useNavigate()

  const tableMap = useMemo(() => Object.fromEntries(tables.map((t) => [t.id, t])), [tables])

  const load = async () => {
    setLoading(true)
    try {
      const r = await getAllCustomMonitors()
      setMonitors((r.data || []).map((m) => ({ ...m, _tableId: m.table_id })))
    } catch (e) {
      toast.error('Failed to load custom monitors')
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [refreshKey])

  const handleRunNow = async (m) => {
    setRunningId(m.id)
    try {
      const r = await runCustomMonitorNow(m._tableId, m.id)
      const d = r.data
      if (d.error) {
        toast.error(`Run error: ${d.error}`)
      } else if (d.passed) {
        toast.success(`${m.name}: 0 violations`)
      } else {
        toast.warning(`${m.name}: ${d.violation_count} violation${d.violation_count !== 1 ? 's' : ''} found`)
      }
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Run failed')
    } finally { setRunningId(null) }
  }

  const handleDelete = async (m) => {
    if (!window.confirm(`Delete monitor "${m.name}"? This cannot be undone.`)) return
    setDeletingId(m.id)
    try {
      await deleteCustomMonitor(m._tableId, m.id)
      toast.success('Monitor deleted')
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to delete monitor')
    } finally { setDeletingId(null) }
  }

  const renderLastResult = (m) => {
    if (!m.last_run_at) return <span className="text-xs text-muted-foreground">Never run</span>
    const passed = m.last_result?.passed ?? (m.last_result?.violation_count === 0)
    const count = m.last_result?.violation_count ?? 0
    return passed
      ? <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400"><CheckCircle2 className="size-3.5" />passed</span>
      : <span className="inline-flex items-center gap-1 text-xs text-orange-600 dark:text-orange-400"><AlertTriangle className="size-3.5" />{count} violations</span>
  }

  if (loading) return (
    <Card>
      <CardHeader><CardTitle className="text-base">Custom SQL Monitors</CardTitle></CardHeader>
      <CardContent><div className="flex flex-col gap-2">{[1,2,3].map(i => <div key={i} className="h-10 animate-pulse rounded-lg border bg-muted/40" />)}</div></CardContent>
    </Card>
  )

  if (monitors.length === 0) return (
    <Card>
      <CardHeader><CardTitle className="text-base">Custom SQL Monitors</CardTitle></CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">No custom SQL monitors yet. Click "Add monitor" to create one, or visit a table's detail page.</p>
      </CardContent>
    </Card>
  )

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Custom SQL Monitors</CardTitle></CardHeader>
      <CardContent>
        <div className="dw-table-wrap">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Table</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Last Result</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {monitors.map((m) => {
                const t = tableMap[m._tableId]
                return (
                  <TableRow key={m.id}>
                    <TableCell>
                      <span className="font-medium text-sm">{m.name}</span>
                      {!m.is_active && <Badge variant="outline" className="ml-2 text-xs">inactive</Badge>}
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        className="font-mono text-xs text-muted-foreground hover:text-foreground transition-colors"
                        onClick={() => t && nav(`/tables/${t.id}`)}
                      >
                        {t ? `${t.schema_name}.${t.table_name}` : m._tableId}
                      </button>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={SEVERITY_BADGE_CLASSES[m.severity] || ''}>{m.severity}</Badge>
                    </TableCell>
                    <TableCell>{renderLastResult(m)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button size="sm" variant="ghost" onClick={() => handleRunNow(m)} disabled={runningId === m.id} className="h-7 px-2">
                          {runningId === m.id ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleDelete(m)} disabled={deletingId === m.id} className="h-7 px-2 text-destructive hover:text-destructive">
                          {deletingId === m.id ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function AutopilotOverview({ rows }) {
  const counts = rows.reduce((acc, row) => {
    const status = row.autopilot?.status || 'not_started'
    acc[status] = (acc[status] || 0) + 1
    const staged = row.autopilot?.steps?.recommendations?.staged_count || 0
    acc.staged += staged
    return acc
  }, { ready: 0, queued: 0, profiling_complete: 0, not_started: 0, staged: 0 })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          Monitor Autopilot
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="text-xs text-muted-foreground">Ready</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{counts.ready}</div>
        </div>
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="text-xs text-muted-foreground">Running</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{counts.queued + counts.profiling_complete}</div>
        </div>
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="text-xs text-muted-foreground">Staged AI monitors</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{counts.staged}</div>
        </div>
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="text-xs text-muted-foreground">Need setup</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{counts.not_started}</div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function Monitors() {
  const nav = useNavigate()
  const [tables, setTables] = useState([])
  const [sources, setSources] = useState([])
  const [status, setStatus] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCustomMonitorDialog, setShowCustomMonitorDialog] = useState(false)
  const [customMonitorsRefreshKey, setCustomMonitorsRefreshKey] = useState(0)

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
            <Button type="button" onClick={() => setShowCustomMonitorDialog(true)}>
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

      <AutopilotOverview rows={monitorRows} />

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
                    <TableHead>Autopilot</TableHead>
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
                      <TableCell>
                        <div className="flex max-w-xs flex-col gap-1">
                          <span className="inline-flex items-center gap-1 text-xs font-medium">
                            <ShieldCheck className="size-3.5 text-primary" />
                            {String(row.autopilot?.status || 'not started').replaceAll('_', ' ')}
                          </span>
                          {row.autopilot?.recommended_next_action && (
                            <span className="line-clamp-2 text-xs text-muted-foreground">{row.autopilot.recommended_next_action}</span>
                          )}
                        </div>
                      </TableCell>
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

      {!loading && tables.length > 0 && (
        <CustomMonitorsTable tables={tables} refreshKey={customMonitorsRefreshKey} />
      )}

      <CustomMonitorDialog
        open={showCustomMonitorDialog}
        onClose={() => setShowCustomMonitorDialog(false)}
        sources={sources}
        tables={tables}
        onCreated={() => setCustomMonitorsRefreshKey((k) => k + 1)}
      />
    </div>
  )
}
