import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, AlertTriangle, Bell, CheckCircle2, Code2, Edit3, Info, Loader2, Play, PlusCircle, RefreshCw, Search, ShieldCheck, Sparkles, Trash2, Wand2 } from 'lucide-react'
import { getIncidents, getSources, getTable, getTableCheckResults, getTableProfiles, nlRule, recommendMonitors, runTable, getCustomMonitors, createCustomMonitor, updateCustomMonitor, updateTable, deleteCustomMonitor, runCustomMonitorNow, runCustomCheck, retryAutopilot, getAlerts, getAlertChannels, createAlert, deleteAlert, testAlert } from '../api/endpoints'
import { toast } from 'sonner'
import HealthBadge from '../components/HealthBadge'
import MetricChart from '../components/MetricChart'
import RefreshBar from '../components/RefreshBar'
import SeverityBadge from '../components/SeverityBadge'
import { useAutoRefresh } from '../hooks/useAutoRefresh'
import { EmptyState, LoadingState, PageHeader, formatDateTime, formatNumber } from '../components/app-ui'
import { notify } from '@/lib/notify'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

// ── Monitor type metadata ─────────────────────────────────────────────────────

const MONITOR_DESCRIPTIONS = {
  row_count: 'Detects when a table becomes completely empty — the most critical data quality signal.',
  freshness: 'Monitors how recently data arrived using the freshness timestamp column. Fires when data stops flowing.',
  schema_drift: 'Automatically detects column additions, removals, and type changes between profiling runs.',
  null_spike: 'Fires when a column\'s null rate jumps by more than 20 percentage points in a single profile.',
  z_score: 'Flags metrics that deviate more than N standard deviations from the 14-day rolling average.',
  isolation_forest: 'ML-based multivariate detector. Spots unusual combinations of metrics. Needs 21+ profiles.',
  stl_seasonal: 'Detects row count anomalies while accounting for weekly seasonality. Needs 21+ days of history.',
  cardinality_drop: 'Alerts when a column\'s distinct value count drops significantly — signs of data truncation or load failure.',
  row_growth: 'Flags unusual spikes or drops in how fast new rows are being added.',
  enum_drift: 'Detects unexpected category values in text columns with a known set of valid values.',
  distribution_drift: 'Monitors shifts in numeric column distributions — percentiles, mean, and spread.',
  null_rate_trend: 'Detects a gradual, sustained increase in null rates over time — distinct from a sudden spike.',
  uniqueness: 'Checks for duplicate values in columns that should be unique.',
  cusum: 'CUSUM detects small but persistent deviations accumulating over time — catches slow data degradation.',
  mann_kendall: 'Mann-Kendall test detects sustained directional trends (steadily increasing or decreasing values).',
  percentile_drift: 'Monitors shifts in p25, p50, p75, p95 percentiles of numeric columns.',
  custom_sql: 'A user-defined SQL query that counts violations. Fires when the count is greater than zero.',
  value_range: 'Checks that numeric values stay within an expected minimum and maximum range.',
}

function MonitorTypeBadge({ type, className }) {
  const description = MONITOR_DESCRIPTIONS[type] || type
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-mono cursor-help ${className || ''}`}
      title={description}
    >
      {type}
    </span>
  )
}

// ── AI Monitor Recommender ────────────────────────────────────────────────────

function friendlyRecommendError(err) {
  const detail = err?.response?.data?.detail || err?.message || ''
  const lower = detail.toLowerCase()
  if (lower.includes('failed to resolve host') || lower.includes('unreachable') || lower.includes('connection refused') || lower.includes('timed out')) {
    return 'Cannot reach the data source. Check your connection settings.'
  }
  return 'Recommendations temporarily unavailable. You can set up monitoring manually.'
}

const SEVERITY_COLORS = { P1: 'text-red-600 dark:text-red-400', P2: 'text-orange-600 dark:text-orange-400', P3: 'text-yellow-600 dark:text-yellow-400' }

function quoteSqlIdent(identifier) {
  return `"${String(identifier || '').replaceAll('"', '""')}"`
}

function qualifiedTableName(tableName) {
  const parts = String(tableName || '').split('.').filter(Boolean)
  if (parts.length >= 2) return `${quoteSqlIdent(parts[0])}.${quoteSqlIdent(parts.slice(1).join('.'))}`
  return quoteSqlIdent(parts[0] || tableName)
}

function intervalFromConfig(config = {}) {
  const raw = config.max_lag || config.max_age || config.max_age_hours || config.max_lag_hours || '24 hours'
  if (typeof raw === 'number') return `${raw} hours`
  const text = String(raw).trim()
  if (/^\d+$/.test(text)) return `${text} hours`
  if (/^\d+\s*(m|min|minute|minutes)$/i.test(text)) return text.replace(/m$/i, ' minutes')
  if (/^\d+\s*(h|hr|hour|hours)$/i.test(text)) return text.replace(/h$/i, ' hours').replace(/hr$/i, ' hours')
  if (/^\d+\s*(d|day|days)$/i.test(text)) return text.replace(/d$/i, ' days')
  return '24 hours'
}

function recommendationSql(rec, tableName) {
  const table = qualifiedTableName(tableName)
  const column = rec.column_name ? quoteSqlIdent(rec.column_name) : null
  const config = rec.config || {}

  if (rec.monitor_type === 'null_rate' && column) {
    return `SELECT COUNT(*) AS violations FROM ${table} WHERE ${column} IS NULL`
  }
  if (rec.monitor_type === 'row_count') {
    const minRows = Number.isFinite(Number(config.min_rows ?? config.min_threshold))
      ? Number(config.min_rows ?? config.min_threshold)
      : 1
    return `SELECT CASE WHEN COUNT(*) < ${minRows} THEN 1 ELSE 0 END AS violations FROM ${table}`
  }
  if (rec.monitor_type === 'duplicate') {
    const columns = Array.isArray(config.key_columns) && config.key_columns.length > 0
      ? config.key_columns
      : rec.column_name ? [rec.column_name] : []
    if (columns.length === 0) return ''
    const groupBy = columns.map(quoteSqlIdent).join(', ')
    return `SELECT COUNT(*) AS violations FROM (SELECT ${groupBy} FROM ${table} GROUP BY ${groupBy} HAVING COUNT(*) > 1) duplicate_keys`
  }
  if (rec.monitor_type === 'freshness' && column) {
    return `SELECT CASE WHEN MAX(${column}) IS NULL OR MAX(${column}) < NOW() - INTERVAL '${intervalFromConfig(config)}' THEN 1 ELSE 0 END AS violations FROM ${table}`
  }
  if (rec.monitor_type === 'value_range' && column) {
    const clauses = []
    // LLM may use min/max OR min_value/max_value — support both
    const minVal = config.min_value ?? config.min
    const maxVal = config.max_value ?? config.max
    if (minVal != null && minVal !== '') clauses.push(`${column} < ${Number(minVal)}`)
    if (maxVal != null && maxVal !== '' && String(maxVal).toUpperCase() !== 'NOW()') clauses.push(`${column} > ${Number(maxVal)}`)
    if (String(maxVal).toUpperCase() === 'NOW()') clauses.push(`${column} > NOW()`)
    if (clauses.length === 0) return ''
    return `SELECT COUNT(*) AS violations FROM ${table} WHERE ${clauses.join(' OR ')}`
  }
  if (rec.monitor_type === 'enum_drift' && column) {
    const allowed = Array.isArray(config.allowed_values) && config.allowed_values.length > 0
      ? config.allowed_values.map(v => `'${String(v).replace(/'/g, "''")}'`).join(', ')
      : null
    if (!allowed) return ''
    return `SELECT COUNT(*) AS violations FROM ${table} WHERE ${column} IS NOT NULL AND ${column} NOT IN (${allowed})`
  }
  if (rec.monitor_type === 'custom_sql') {
    return String(config.sql || config.sql_query || rec.sql_query || '').trim()
  }
  // schema_drift is managed by the profiler (fingerprint diff) — no SQL equivalent
  return ''
}

function AutopilotPanel({ table, onMonitorSaved, onRefreshTable }) {
  const [applying, setApplying] = useState({})
  const [addingSafe, setAddingSafe] = useState({})
  const [retrying, setRetrying] = useState(false)
  const state = table?.autopilot
  if (!state) return null

  const steps = state.steps || {}
  const safeMonitors = state.safe_monitors || []
  const recommendations = state.recommendations || []
  const isFailed = state.status === 'failed'
  const isNotStarted = state.status === 'not_started'
  // Only show Retry/Run button when truly failed or never started — NOT when queued/in-progress
  const recStatus = steps.recommendations?.status
  const isQueued = false // tasks run automatically; never prompt user to start them manually
  const stepEntries = [
    ['profile', 'First profile'],
    ['safe_baseline', 'Safe baseline monitors'],
    ['recommendations', 'AI monitor recommendations'],
    ['alerts', 'Alert routing'],
  ].map(([key, fallback]) => [key, steps[key] || { label: fallback, status: 'pending' }])

  const handleRetry = async () => {
    setRetrying(true)
    try {
      await retryAutopilot(table.id)
      notify.ok('Autopilot requeued — refreshing in a few seconds…')
      setTimeout(() => onRefreshTable?.(), 3000)
    } catch (e) {
      notify.err(e?.response?.data?.detail || 'Failed to retry autopilot')
    } finally {
      setRetrying(false)
    }
  }

  const applyRecommendation = async (rec, index) => {
    setApplying((prev) => ({ ...prev, [rec.id || index]: true }))
    try {
      const sql = recommendationSql(rec, `${table.schema_name}.${table.table_name}`)
      if (!sql) {
        notify.err('This recommendation needs review before it can become a SQL monitor.')
        return
      }
      await createCustomMonitor(table.id, {
        name: rec.name || 'AI recommended monitor',
        description: rec.rationale || 'Staged by table autopilot',
        sql_query: sql,
        severity: rec.severity || 'P3',
        run_on_profile: true,
      })
      notify.ok('Monitor added', rec.name)
      onMonitorSaved?.()
    } catch (e) {
      notify.err(e?.response?.data?.detail || 'Failed to add monitor')
    } finally {
      setApplying((prev) => {
        const next = { ...prev }
        delete next[rec.id || index]
        return next
      })
    }
  }

  const addSafeMonitor = async (monitor, index) => {
    setAddingSafe((prev) => ({ ...prev, [index]: true }))
    try {
      const sql = recommendationSql(monitor, `${table.schema_name}.${table.table_name}`)
      if (!sql) {
        notify.err('Cannot generate SQL for this monitor type.')
        return
      }
      await createCustomMonitor(table.id, {
        name: monitor.name || monitor.monitor_type,
        description: monitor.rationale || `Built-in ${monitor.monitor_type} monitor`,
        sql_query: sql,
        severity: monitor.severity || 'P2',
        run_on_profile: true,
      })
      notify.ok('Monitor added', monitor.name)
      onMonitorSaved?.()
    } catch (e) {
      notify.err(e?.response?.data?.detail || 'Failed to add monitor')
    } finally {
      setAddingSafe((prev) => {
        const next = { ...prev }
        delete next[index]
        return next
      })
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base flex items-center gap-2">
          <ShieldCheck className="size-4 text-primary" />
          Table Autopilot
        </CardTitle>
        {(isFailed || isNotStarted) && (
          <Button size="sm" variant="outline" onClick={handleRetry} disabled={retrying}>
            {retrying ? <Loader2 className="size-3.5 animate-spin mr-1" /> : <RefreshCw className="size-3.5 mr-1" />}
            {isFailed ? 'Retry' : 'Run AI analysis'}
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {stepEntries.map(([key, step]) => (
            <div key={key} className="rounded-md border bg-muted/20 px-3 py-2">
              <div className="flex items-center gap-2">
                {['complete', 'enabled', 'ready'].includes(step.status) ? (
                  <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" />
                ) : step.status === 'failed' ? (
                  <AlertTriangle className="size-4 text-destructive" />
                ) : step.status === 'queued' || step.status === 'pending' ? (
                  <Loader2 className="size-4 text-muted-foreground animate-spin" />
                ) : step.status === 'needs_review' ? (
                  <Info className="size-4 text-blue-500" />
                ) : (
                  <AlertTriangle className="size-4 text-amber-600 dark:text-amber-400" />
                )}
                <span className="text-sm font-medium">{step.label}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {step.status === 'queued' ? 'working in background…'
                  : step.status === 'pending' ? 'waiting…'
                  : step.status === 'profiling_complete' ? 'profile done'
                  : step.status === 'needs_review' ? 'action needed'
                  : String(step.status || 'pending').replaceAll('_', ' ')}
              </p>
            </div>
          ))}
        </div>

        {state.recommended_next_action && !isFailed && state.status !== 'not_started' && (
          <p className="rounded-md border bg-muted/20 px-3 py-2 text-sm text-muted-foreground">{state.recommended_next_action}</p>
        )}
        {(state.status === 'queued' || state.status === 'profiling_complete') && (
          <p className="rounded-md border bg-blue-500/10 border-blue-500/20 px-3 py-2 text-sm text-blue-600 dark:text-blue-400">
            AI analysis is running in the background — no action needed. This page will reflect progress automatically.
          </p>
        )}

        {safeMonitors.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Baseline monitors (auto-enabled by AI)</p>
            <div className="flex flex-col gap-2">
              {safeMonitors.map((monitor, index) => {
                const sql = recommendationSql(monitor, `${table.schema_name}.${table.table_name}`)
                return (
                  <div key={`${monitor.name}-${index}`} className="rounded-md border bg-muted/10 px-3 py-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className={SEVERITY_BADGE_CLASSES[monitor.severity] || ''}>{monitor.severity || 'P2'}</Badge>
                      <span className="text-sm font-medium">{monitor.name || monitor.monitor_type}</span>
                      <Badge variant="secondary" className="font-mono text-xs">{monitor.monitor_type}</Badge>
                      {sql ? (
                        <Button size="sm" variant="outline" className="ml-auto" disabled={!!addingSafe[index]} onClick={() => addSafeMonitor(monitor, index)}>
                          {addingSafe[index] ? <Loader2 className="size-3.5 animate-spin" /> : 'Add as monitor'}
                        </Button>
                      ) : (
                        <span className="ml-auto text-xs text-muted-foreground italic">Profiler-managed</span>
                      )}
                    </div>
                    {monitor.rationale && <p className="mt-1 text-xs text-muted-foreground">{monitor.rationale}</p>}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {recommendations.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">AI recommendations — staged for review</p>
            {recommendations.map((rec, index) => {
              const key = rec.id || index
              return (
                <div key={key} className="rounded-md border bg-muted/10 px-3 py-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className={SEVERITY_BADGE_CLASSES[rec.severity] || ''}>{rec.severity || 'P3'}</Badge>
                    <span className="text-sm font-medium">{rec.name}</span>
                    <Badge variant="secondary" className="font-mono text-xs">{rec.monitor_type}</Badge>
                    <Button size="sm" variant="outline" className="ml-auto" disabled={applying[key]} onClick={() => applyRecommendation(rec, index)}>
                      {applying[key] ? <Loader2 className="size-3.5 animate-spin" /> : 'Add monitor'}
                    </Button>
                  </div>
                  {rec.rationale && <p className="mt-1 text-xs text-muted-foreground">{rec.rationale}</p>}
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function AIMonitorRecommender({ tableId, sourceId, tableName, hasMonitors, onMonitorSaved, existingMonitorCount = 0 }) {
  const [recs, setRecs] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dismissed, setDismissed] = useState(false)
  const [applying, setApplying] = useState({})
  const [applied, setApplied] = useState({})
  const dismissKey = `dw_rec_dismissed_${tableId}`

  // Auto-trigger when no monitors exist and not previously dismissed this session
  // Guard: only run once sourceId is resolved (table data has loaded)
  useEffect(() => {
    if (!sourceId) return
    if (hasMonitors) return
    if (sessionStorage.getItem(dismissKey)) return
    run()
  }, [tableId, sourceId, hasMonitors])

  const run = async () => {
    if (!sourceId) return
    setLoading(true); setError(''); setRecs(null)
    try {
      const r = await recommendMonitors(sourceId, {
        table_name: tableName.split('.')[1] || tableName,
        schema_name: tableName.split('.')[0] || 'public',
        table_id: tableId,
      })
      setRecs(r.data.recommendations || [])
    } catch (e) {
      setError(friendlyRecommendError(e))
    } finally { setLoading(false) }
  }

  const dismiss = () => {
    setDismissed(true)
    sessionStorage.setItem(dismissKey, '1')
  }

  const applyRec = async (rec, index) => {
    setApplying((prev) => ({ ...prev, [index]: true }))
    try {
      const sql = recommendationSql(rec, tableName)
      if (!sql) {
        notify.err('This recommendation needs manual setup before it can be saved as a SQL monitor.')
        return
      }
      await createCustomMonitor(tableId, {
        name: rec.name || `${rec.monitor_type} monitor`,
        description: rec.rationale || `AI recommended ${rec.monitor_type} monitor`,
        sql_query: sql,
        severity: rec.severity || 'P3',
        run_on_profile: true,
      })
      setApplied((prev) => ({ ...prev, [index]: true }))
      onMonitorSaved?.()
      notify.ok('Monitor added', rec.name)
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Failed to add monitor'
      notify.err(msg)
    } finally {
      setApplying((prev) => { const next = { ...prev }; delete next[index]; return next })
    }
  }

  if (dismissed && !recs && !loading) return null

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Let AI analyze your table schema and suggest monitors.</p>
        <Button size="sm" variant="outline" onClick={run} disabled={loading}>
          {loading ? <Loader2 className="size-3.5 animate-spin" /> : (recs ? 'Regenerate' : 'Generate')}
        </Button>
      </div>
      {loading && (
        <div className="flex flex-col gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg border bg-muted/40" />
          ))}
        </div>
      )}
      {!loading && error && (
        <p className="text-sm text-muted-foreground">{error}</p>
      )}
      {!loading && !recs && !error && null}
      {!loading && recs?.length === 0 && (
        <p className="text-sm text-muted-foreground">No recommendations generated for this table.</p>
      )}
      {!loading && recs && recs.length > 0 && (
        <div className="flex flex-col gap-2">
          {recs.map((r, i) => (
            <div key={i} className="rounded-lg border bg-muted/20 px-3 py-2.5 flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold ${SEVERITY_COLORS[r.severity] || ''}`}>{r.severity}</span>
                <span className="text-sm font-medium">{r.name}</span>
                <MonitorTypeBadge type={r.monitor_type} />
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
  )
}

// ── Built-in Monitors Panel ───────────────────────────────────────────────────

const BUILTIN_CHECK_GROUPS = [
  {
    key: 'core',
    label: 'Core monitors',
    description: 'Always active — these checks power P1/P2 incident detection and cannot be disabled.',
    checks: [
      { id: 'row_count', label: 'Empty table detection', description: MONITOR_DESCRIPTIONS.row_count },
      { id: 'freshness', label: 'Freshness monitoring', description: MONITOR_DESCRIPTIONS.freshness, requiresFreshnessColumn: true },
      { id: 'schema_drift', label: 'Schema drift', description: MONITOR_DESCRIPTIONS.schema_drift },
      { id: 'null_spike', label: 'Null rate spike', description: MONITOR_DESCRIPTIONS.null_spike },
    ],
    alwaysOn: true,
  },
  {
    key: 'statistical',
    label: 'Statistical checks',
    checks: [
      { id: 'z_score', label: 'Z-score anomaly detection', description: MONITOR_DESCRIPTIONS.z_score },
      { id: 'row_growth', label: 'Row growth rate', description: MONITOR_DESCRIPTIONS.row_growth },
    ],
  },
  {
    key: 'ml',
    label: 'ML-based detection',
    checks: [
      { id: 'isolation_forest', label: 'Isolation Forest', description: MONITOR_DESCRIPTIONS.isolation_forest },
      { id: 'stl_seasonal', label: 'STL seasonal decomposition', description: MONITOR_DESCRIPTIONS.stl_seasonal },
    ],
  },
  {
    key: 'column',
    label: 'Column-level checks',
    checks: [
      { id: 'cardinality_drop', label: 'Cardinality drop', description: MONITOR_DESCRIPTIONS.cardinality_drop },
      { id: 'enum_drift', label: 'Enum / category drift', description: MONITOR_DESCRIPTIONS.enum_drift },
      { id: 'distribution_drift', label: 'Distribution drift', description: MONITOR_DESCRIPTIONS.distribution_drift },
      { id: 'null_rate_trend', label: 'Null rate trend', description: MONITOR_DESCRIPTIONS.null_rate_trend },
      { id: 'uniqueness', label: 'Uniqueness checks', description: MONITOR_DESCRIPTIONS.uniqueness },
    ],
  },
  {
    key: 'advanced',
    label: 'Advanced analytics',
    checks: [
      { id: 'cusum', label: 'CUSUM change detection', description: MONITOR_DESCRIPTIONS.cusum },
      { id: 'mann_kendall', label: 'Mann-Kendall trend', description: MONITOR_DESCRIPTIONS.mann_kendall },
      { id: 'percentile_drift', label: 'Percentile drift', description: MONITOR_DESCRIPTIONS.percentile_drift },
    ],
  },
]

function BuiltinMonitorsPanel({ table, onSave }) {
  const checkConfig = table.check_config || {}
  const [disabledChecks, setDisabledChecks] = useState(new Set(checkConfig.disabled_checks || []))
  const [disabledColumns, setDisabledColumns] = useState(new Set(checkConfig.disabled_columns || []))
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  const columns = Object.keys(table.latest_profile?.column_metrics || {})

  const toggleCheck = (id) => {
    setDisabledChecks(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
    setDirty(true)
  }

  const toggleColumn = (col) => {
    setDisabledColumns(prev => {
      const next = new Set(prev)
      if (next.has(col)) next.delete(col); else next.add(col)
      return next
    })
    setDirty(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateTable(table.id, {
        check_config: {
          disabled_checks: Array.from(disabledChecks),
          disabled_columns: Array.from(disabledColumns),
        }
      })
      setDirty(false)
      onSave?.()
      toast.success('Monitor configuration saved')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="size-4 text-muted-foreground" />
          Built-in monitors
        </CardTitle>
        {dirty && (
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="size-3.5 animate-spin mr-1" /> : null}
            Save changes
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {BUILTIN_CHECK_GROUPS.map(group => (
          <div key={group.key} className="flex flex-col gap-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.label}</p>
              {group.description && <p className="text-xs text-muted-foreground mt-0.5">{group.description}</p>}
            </div>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {group.checks.map(check => {
                if (check.requiresFreshnessColumn && !table.freshness_column) return null
                const enabled = group.alwaysOn || !disabledChecks.has(check.id)
                return (
                  <div
                    key={check.id}
                    className={`flex items-start gap-3 rounded-md border px-3 py-2 ${group.alwaysOn ? 'bg-muted/10 opacity-75' : 'cursor-pointer hover:bg-muted/20'}`}
                    onClick={group.alwaysOn ? undefined : () => toggleCheck(check.id)}
                    title={check.description}
                  >
                    <div className={`mt-0.5 size-4 shrink-0 rounded-sm border-2 flex items-center justify-center ${enabled ? 'bg-primary border-primary' : 'border-muted-foreground/40'}`}>
                      {enabled && <span className="text-primary-foreground text-[10px] font-bold leading-none">✓</span>}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium leading-snug">{check.label}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{check.description}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}

        {columns.length > 0 && (
          <div className="flex flex-col gap-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Column exclusions</p>
              <p className="text-xs text-muted-foreground mt-0.5">Columns checked here will be excluded from all column-level monitoring checks.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {columns.map(col => {
                const excluded = disabledColumns.has(col)
                return (
                  <button
                    key={col}
                    type="button"
                    onClick={() => toggleColumn(col)}
                    className={`rounded-full border px-2.5 py-1 text-xs font-mono transition-colors ${excluded ? 'bg-muted/60 text-muted-foreground line-through border-muted' : 'bg-background text-foreground border hover:bg-muted/40'}`}
                  >
                    {col}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Natural Language Rule Builder ─────────────────────────────────────────────

const SEVERITY_BADGE_CLASSES = {
  P1: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  P2: 'border-orange-600/25 bg-orange-600/10 text-orange-700 dark:text-orange-300',
  P3: 'border-yellow-600/25 bg-yellow-600/10 text-yellow-700 dark:text-yellow-300',
}

function NLRuleBuilder({ tableId, tableName, onMonitorSaved }) {
  const [rule, setRule] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showSaveForm, setShowSaveForm] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [sqlDraft, setSqlDraft] = useState('')
  const [severityDraft, setSeverityDraft] = useState('P3')
  const [lastTestedSql, setLastTestedSql] = useState('')

  const generate = async (e) => {
    e.preventDefault()
    if (!rule.trim()) return
    setLoading(true); setError(''); setResult(null); setTestResult(null); setShowSaveForm(false); setSqlDraft(''); setLastTestedSql('')
    try {
      const r = await nlRule(tableId, { rule, table_name: tableName })
      setResult(r.data)
      setSqlDraft(r.data.sql || '')
      setSeverityDraft(r.data.severity || 'P3')
      setSaveName(rule)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to generate SQL — LLM key may not be configured.')
    } finally { setLoading(false) }
  }

  const testSql = async () => {
    const sql = sqlDraft.trim()
    if (!sql) return
    setTesting(true); setTestResult(null)
    try {
      const r = await runCustomCheck(tableId, { sql, name: rule, severity: severityDraft })
      setTestResult(r.data)
      setLastTestedSql(sql)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Test run failed')
    } finally { setTesting(false) }
  }

  const saveAsMonitor = async () => {
    const sql = sqlDraft.trim()
    if (!sql || !saveName.trim() || lastTestedSql !== sql || !testResult) return
    setSaving(true)
    try {
      await createCustomMonitor(tableId, {
        name: saveName.trim(),
        sql_query: sql,
        severity: severityDraft,
        description: [rule, result?.explanation].filter(Boolean).join(' — '),
        run_on_profile: true,
      })
      toast.success('Monitor saved successfully')
      setShowSaveForm(false)
      setResult(null)
      setRule('')
      setTestResult(null)
      setSqlDraft('')
      setLastTestedSql('')
      onMonitorSaved?.()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to save monitor')
    } finally { setSaving(false) }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Wand2 className="size-4 text-primary" />
        <p className="text-sm font-medium">Natural language rule builder</p>
      </div>
      <p className="text-sm text-muted-foreground">Describe a business rule in plain English. AI converts it to a SQL check that counts violations.</p>
        <form onSubmit={generate} className="flex gap-2">
          <input
            className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
            placeholder="e.g. Paid orders must have a payment reference"
            value={rule}
            onChange={e => setRule(e.target.value)}
          />
          <Button type="submit" size="sm" disabled={loading || !rule.trim()}>
            {loading ? <><Loader2 className="size-3.5 animate-spin mr-1" />Generating…</> : 'Generate'}
          </Button>
        </form>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {result?.sql && (
          <div className="flex flex-col gap-3">
            <div className="rounded-lg bg-muted/60 border p-3">
              <div className="flex items-center gap-2 mb-2">
                <Code2 className="size-3.5 text-muted-foreground" />
                <label htmlFor="nl-generated-sql" className="text-xs text-muted-foreground font-semibold uppercase tracking-wide">Generated SQL (violation count)</label>
              </div>
              <textarea
                id="nl-generated-sql"
                aria-label="Generated SQL"
                className="min-h-[96px] w-full resize-y rounded-md border bg-background px-3 py-2 text-xs font-mono leading-relaxed text-foreground outline-none focus:ring-1 focus:ring-primary"
                value={sqlDraft}
                onChange={(e) => {
                  setSqlDraft(e.target.value)
                  setTestResult(null)
                  setLastTestedSql('')
                }}
              />
            </div>
            {result.explanation && <p className="text-sm text-muted-foreground">{result.explanation}</p>}
            <div className="flex items-center gap-3 flex-wrap">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                Severity
                <select
                  className="rounded-md border bg-background px-2 py-1 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
                  value={severityDraft}
                  onChange={(e) => setSeverityDraft(e.target.value)}
                >
                  <option value="P1">P1</option>
                  <option value="P2">P2</option>
                  <option value="P3">P3</option>
                </select>
              </label>
              <Badge variant="outline" className={SEVERITY_BADGE_CLASSES[severityDraft] || ''}>
                {severityDraft}
              </Badge>
              {result.estimated_impact && (
                <span className="text-xs text-muted-foreground">Impact: {result.estimated_impact}</span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Button size="sm" variant="outline" onClick={testSql} disabled={testing || !sqlDraft.trim()}>
                {testing ? <Loader2 className="size-3.5 animate-spin mr-1" /> : <Play className="size-3.5 mr-1" />}
                Test SQL
              </Button>
              {testResult != null && (
                <span className={`text-sm font-medium flex items-center gap-1 ${testResult.passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-orange-600 dark:text-orange-400'}`}>
                  {testResult.passed
                    ? <><CheckCircle2 className="size-4" /> 0 violations</>
                    : <><AlertTriangle className="size-4" /> {testResult.violation_count} violation{testResult.violation_count !== 1 ? 's' : ''} found</>
                  }
                </span>
              )}
              <Button size="sm" variant="outline" onClick={() => setShowSaveForm((v) => !v)}>
                <PlusCircle className="size-3.5 mr-1" />
                Save as Monitor
              </Button>
            </div>
            {showSaveForm && (
              <div className="rounded-lg border bg-muted/20 p-3 flex flex-col gap-2">
                <p className="text-xs font-medium text-muted-foreground">Monitor name</p>
                <div className="flex gap-2">
                  <input
                    className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                    value={saveName}
                    onChange={e => setSaveName(e.target.value)}
                    placeholder="Monitor name"
                  />
                  <Button size="sm" onClick={saveAsMonitor} disabled={saving || !saveName.trim() || lastTestedSql !== sqlDraft.trim() || !testResult}>
                    {saving ? <Loader2 className="size-3.5 animate-spin" /> : 'Save'}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowSaveForm(false)}>Cancel</Button>
                </div>
              </div>
            )}
          </div>
        )}
    </div>
  )
}

// ── Alert Routing ─────────────────────────────────────────────────────────────

const CHANNEL_LABELS = { slack: 'Slack', email: 'Email', pagerduty: 'PagerDuty' }

function AlertRoutingPanel({ tableId }) {
  const [alerts, setAlerts] = useState([])
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [channel, setChannel] = useState('slack')
  const [minSeverity, setMinSeverity] = useState('P3')
  const [config, setConfig] = useState({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const load = async () => {
    try {
      const [alertsRes, channelsRes] = await Promise.all([getAlerts(), getAlertChannels()])
      setAlerts((alertsRes.data || []).filter(a => a.table_id === tableId || !a.table_id))
      const chs = channelsRes.data?.channels || []
      setChannels(chs)
      // Set default channel to first available
      const first = chs.find(c => c.available)
      if (first) setChannel(first.id)
    } catch (e) {
      // silently skip
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [tableId])

  const tableAlerts = alerts.filter(a => a.table_id === tableId)
  const workspaceAlerts = alerts.filter(a => !a.table_id)
  const availableChannels = channels.filter(c => c.available)

  const resetForm = () => {
    const firstChannel = availableChannels[0]?.id || 'email'
    setChannel(firstChannel); setMinSeverity('P3'); setConfig({}); setShowForm(false)
  }

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await createAlert({ table_id: tableId, channel, config: { ...config, min_severity: minSeverity } })
      notify.ok('Alert route added')
      resetForm()
      load()
    } catch (e) {
      notify.err(e?.response?.data?.detail || 'Failed to create alert route')
    } finally { setSaving(false) }
  }

  const handleTest = async (alertId) => {
    setTesting(alertId)
    try {
      const r = await testAlert(alertId)
      notify.ok(r.data?.message || 'Test alert sent')
    } catch (e) {
      notify.err(e?.response?.data?.detail || 'Test failed')
    } finally { setTesting(null) }
  }

  const handleDelete = async (alertId) => {
    setDeleting(alertId)
    try {
      await deleteAlert(alertId)
      load()
    } catch (e) {
      notify.err(e?.response?.data?.detail || 'Failed to remove')
    } finally { setDeleting(null) }
  }

  const renderConfigFields = () => {
    // slack / teams / discord all use webhook_url; generic webhook uses url
    if (channel === 'slack' || channel === 'teams' || channel === 'discord') return (
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground font-medium">Webhook URL *</label>
        <input className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary" required
          placeholder="https://hooks.slack.com/services/..." value={config.webhook_url || ''} onChange={e => setConfig({ ...config, webhook_url: e.target.value })} />
      </div>
    )
    if (channel === 'webhook') return (
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground font-medium">Endpoint URL *</label>
        <input className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary" required
          placeholder="https://webhook.site/..." value={config.url || ''} onChange={e => setConfig({ ...config, url: e.target.value })} />
      </div>
    )
    if (channel === 'email') return (
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground font-medium">Recipient email(s) * (comma-separated)</label>
        <input type="text" className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary" required
          placeholder="oncall@acme.io, team@acme.io" value={config.to || ''} onChange={e => setConfig({ ...config, to: e.target.value })} />
      </div>
    )
    if (channel === 'pagerduty') return (
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground font-medium">PagerDuty routing key *</label>
        <input className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary" required
          placeholder="abc123..." value={config.routing_key || ''} onChange={e => setConfig({ ...config, routing_key: e.target.value })} />
      </div>
    )
    if (channel === 'opsgenie') return (
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground font-medium">OpsGenie API key *</label>
        <input className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary" required
          placeholder="abc123..." value={config.api_key || ''} onChange={e => setConfig({ ...config, api_key: e.target.value })} />
      </div>
    )
    return null
  }

  const renderAlertRow = (a) => (
    <div key={a.id} className="rounded-md border bg-muted/10 px-3 py-2.5 flex items-center gap-2 flex-wrap">
      <Badge variant="outline">{CHANNEL_LABELS[a.channel] || a.channel}</Badge>
      <span className="text-sm text-muted-foreground">≥ {a.min_severity}</span>
      {!a.table_id && <Badge variant="secondary" className="text-xs">workspace</Badge>}
      <div className="ml-auto flex gap-1">
        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={testing === a.id} onClick={() => handleTest(a.id)}>
          {testing === a.id ? <Loader2 className="size-3.5 animate-spin" /> : 'Test'}
        </Button>
        {a.table_id && (
          <Button size="sm" variant="ghost" className="h-7 px-2 text-destructive hover:text-destructive" disabled={deleting === a.id} onClick={() => handleDelete(a.id)}>
            {deleting === a.id ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
          </Button>
        )}
      </div>
    </div>
  )

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base flex items-center gap-2">
          <Bell className="size-4 text-primary" />
          Alert Routing
        </CardTitle>
        {!showForm && availableChannels.length > 0 && (
          <Button size="sm" variant="outline" onClick={() => setShowForm(true)}>
            <PlusCircle className="size-3.5 mr-1" />
            Add route
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {loading && <div className="h-10 animate-pulse rounded-lg border bg-muted/40" />}

        {showForm && (
          <form onSubmit={handleSave} className="rounded-lg border bg-muted/20 p-4 flex flex-col gap-3">
            <p className="text-sm font-medium">New alert route for this table</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">Channel</label>
                <select className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                  value={channel} onChange={e => { setChannel(e.target.value); setConfig({}) }}>
                  {availableChannels.map(c => <option key={c.id} value={c.id}>{c.label || CHANNEL_LABELS[c.id] || c.id}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">Minimum severity</label>
                <select className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                  value={minSeverity} onChange={e => setMinSeverity(e.target.value)}>
                  <option value="P1">P1 only</option>
                  <option value="P2">P2 and above</option>
                  <option value="P3">All (P3+)</option>
                </select>
              </div>
            </div>
            {renderConfigFields()}
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={saving}>{saving ? <Loader2 className="size-3.5 animate-spin" /> : 'Save route'}</Button>
              <Button type="button" size="sm" variant="ghost" onClick={resetForm}>Cancel</Button>
            </div>
          </form>
        )}

        {!loading && tableAlerts.length === 0 && workspaceAlerts.length === 0 && !showForm && (
          <p className="text-sm text-muted-foreground">
            {availableChannels.length === 0
              ? 'No alert channels available on your plan. Upgrade to enable Slack, email, or PagerDuty routing.'
              : 'No alert routes configured for this table. Add one to get notified when incidents are created.'}
          </p>
        )}

        {tableAlerts.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Table-specific routes</p>
            {tableAlerts.map(renderAlertRow)}
          </div>
        )}

        {workspaceAlerts.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Workspace-wide routes (inherited)</p>
            {workspaceAlerts.map(renderAlertRow)}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Custom Monitors ───────────────────────────────────────────────────────────

function CustomMonitors({ tableId, refreshKey = 0 }) {
  const [monitors, setMonitors] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [runningId, setRunningId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [togglingId, setTogglingId] = useState(null)

  // Add form state
  const [addName, setAddName] = useState('')
  const [addDescription, setAddDescription] = useState('')
  const [addSql, setAddSql] = useState('')
  const [addSeverity, setAddSeverity] = useState('P3')
  const [addRunOnProfile, setAddRunOnProfile] = useState(true)
  const [addSaving, setAddSaving] = useState(false)
  const [addTesting, setAddTesting] = useState(false)
  const [addTestResult, setAddTestResult] = useState(null)
  const [addLastTestedSql, setAddLastTestedSql] = useState('')

  // Edit form state
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editSql, setEditSql] = useState('')
  const [editSeverity, setEditSeverity] = useState('P3')
  const [editRunOnProfile, setEditRunOnProfile] = useState(true)
  const [editSaving, setEditSaving] = useState(false)

  const load = async () => {
    try {
      const r = await getCustomMonitors(tableId)
      setMonitors(r.data)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to load custom monitors')
    } finally { setLoading(false) }
  }

  useEffect(() => { setLoading(true); load() }, [tableId, refreshKey])

  const resetAddForm = () => {
    setAddName(''); setAddDescription(''); setAddSql(''); setAddSeverity('P3'); setAddRunOnProfile(true)
    setAddTestResult(null); setAddLastTestedSql('')
    setShowAddForm(false)
  }

  const handleAddSqlChange = (value) => {
    setAddSql(value)
    setAddTestResult(null)
    setAddLastTestedSql('')
  }

  const addSqlTested = addSql.trim() && addLastTestedSql === addSql.trim() && addTestResult

  const testAddSql = async () => {
    const sql = addSql.trim()
    if (!sql) return
    setAddTesting(true)
    setAddTestResult(null)
    try {
      const r = await runCustomCheck(tableId, { sql, name: addName.trim() || 'Custom SQL monitor', severity: addSeverity })
      setAddTestResult(r.data)
      setAddLastTestedSql(sql)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Test run failed')
    } finally {
      setAddTesting(false)
    }
  }

  const handleAdd = async (e) => {
    e.preventDefault()
    if (!addName.trim() || !addSql.trim() || !addSqlTested) return
    setAddSaving(true)
    try {
      await createCustomMonitor(tableId, {
        name: addName.trim(),
        description: addDescription.trim() || undefined,
        sql_query: addSql.trim(),
        severity: addSeverity,
        run_on_profile: addRunOnProfile,
      })
      toast.success('Monitor created')
      resetAddForm()
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to create monitor')
    } finally { setAddSaving(false) }
  }

  const startEdit = (m) => {
    setEditingId(m.id)
    setEditName(m.name)
    setEditDescription(m.description || '')
    setEditSql(m.sql_query)
    setEditSeverity(m.severity)
    setEditRunOnProfile(m.run_on_profile)
  }

  const handleEdit = async (e, monitorId) => {
    e.preventDefault()
    setEditSaving(true)
    try {
      await updateCustomMonitor(tableId, monitorId, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
        sql_query: editSql.trim(),
        severity: editSeverity,
        run_on_profile: editRunOnProfile,
      })
      toast.success('Monitor updated')
      setEditingId(null)
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to update monitor')
    } finally { setEditSaving(false) }
  }

  const handleToggle = async (m) => {
    setTogglingId(m.id)
    try {
      await updateCustomMonitor(tableId, m.id, { is_active: !m.is_active })
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to update monitor')
    } finally { setTogglingId(null) }
  }

  const handleRunNow = async (m) => {
    setRunningId(m.id)
    try {
      const r = await runCustomMonitorNow(tableId, m.id)
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
      await deleteCustomMonitor(tableId, m.id)
      toast.success('Monitor deleted')
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to delete monitor')
    } finally { setDeletingId(null) }
  }

  const renderLastResult = (m) => {
    if (!m.last_run_at) return <span className="text-xs text-muted-foreground">Never run</span>
    if (m.last_result == null) return <span className="text-xs text-muted-foreground">—</span>
    const passed = m.last_result?.passed ?? (m.last_result?.violation_count === 0)
    const count = m.last_result?.violation_count ?? 0
    return passed
      ? <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400"><CheckCircle2 className="size-3.5" />passed</span>
      : <span className="inline-flex items-center gap-1 text-xs text-orange-600 dark:text-orange-400"><AlertTriangle className="size-3.5" />{count} violations</span>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Code2 className="size-4 text-primary" />
          <span className="text-sm font-medium">SQL monitors</span>
        </div>
        <Button size="sm" variant="outline" onClick={() => { setShowAddForm((v) => !v); setEditingId(null) }}>
          <PlusCircle className="size-3.5 mr-1" />
          Add monitor
        </Button>
      </div>
        {showAddForm && (
          <form onSubmit={handleAdd} className="rounded-lg border bg-muted/20 p-4 flex flex-col gap-3">
            <p className="text-sm font-medium">New custom monitor</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">Name *</label>
                <input
                  className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                  value={addName} onChange={e => setAddName(e.target.value)}
                  placeholder="e.g. Paid orders without reference" required
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">Severity</label>
                <select
                  className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                  value={addSeverity} onChange={e => setAddSeverity(e.target.value)}
                >
                  <option value="P1">P1 — Critical</option>
                  <option value="P2">P2 — High</option>
                  <option value="P3">P3 — Medium</option>
                </select>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground font-medium">Description (optional)</label>
              <input
                className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                value={addDescription} onChange={e => setAddDescription(e.target.value)}
                placeholder="What does this check detect?"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground font-medium">SQL query * (must return a count of violations)</label>
              <textarea
                className="rounded-md border bg-background px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-primary min-h-[80px] resize-y"
                value={addSql} onChange={e => handleAddSqlChange(e.target.value)}
                placeholder="SELECT COUNT(*) FROM orders WHERE status = 'paid' AND payment_reference IS NULL"
                required
              />
            </div>
            {addTestResult && (
              <span className={`text-sm font-medium flex items-center gap-1 ${addTestResult.passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-orange-600 dark:text-orange-400'}`}>
                {addTestResult.passed
                  ? <><CheckCircle2 className="size-4" /> 0 violations</>
                  : <><AlertTriangle className="size-4" /> {addTestResult.violation_count} violation{addTestResult.violation_count !== 1 ? 's' : ''} found</>
                }
              </span>
            )}
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={addRunOnProfile} onChange={e => setAddRunOnProfile(e.target.checked)} className="rounded" />
              Run on every profile
            </label>
            <div className="flex gap-2">
              <Button type="button" size="sm" variant="outline" onClick={testAddSql} disabled={addTesting || !addSql.trim()}>
                {addTesting ? <Loader2 className="size-3.5 animate-spin" /> : 'Test SQL'}
              </Button>
              <Button type="submit" size="sm" disabled={addSaving || !addName.trim() || !addSql.trim() || !addSqlTested}>
                {addSaving ? <Loader2 className="size-3.5 animate-spin" /> : 'Save monitor'}
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={resetAddForm}>Cancel</Button>
            </div>
          </form>
        )}

        {loading && <div className="flex flex-col gap-2">{[1, 2].map(i => <div key={i} className="h-12 animate-pulse rounded-lg border bg-muted/40" />)}</div>}

        {!loading && monitors.length === 0 && !showAddForm && (
          <p className="text-sm text-muted-foreground">No custom SQL monitors yet. Click "Add monitor" to create one.</p>
        )}

        {!loading && monitors.length > 0 && (
          <div className="flex flex-col gap-2">
            {monitors.map((m) => (
              <div key={m.id} className="rounded-lg border bg-muted/10">
                {editingId === m.id ? (
                  <form onSubmit={(e) => handleEdit(e, m.id)} className="p-4 flex flex-col gap-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-muted-foreground font-medium">Name *</label>
                        <input
                          className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                          value={editName} onChange={e => setEditName(e.target.value)} required
                        />
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-muted-foreground font-medium">Severity</label>
                        <select
                          className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                          value={editSeverity} onChange={e => setEditSeverity(e.target.value)}
                        >
                          <option value="P1">P1 — Critical</option>
                          <option value="P2">P2 — High</option>
                          <option value="P3">P3 — Medium</option>
                        </select>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs text-muted-foreground font-medium">Description (optional)</label>
                      <input
                        className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                        value={editDescription} onChange={e => setEditDescription(e.target.value)}
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs text-muted-foreground font-medium">SQL query *</label>
                      <textarea
                        className="rounded-md border bg-background px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-primary min-h-[80px] resize-y"
                        value={editSql} onChange={e => setEditSql(e.target.value)} required
                      />
                    </div>
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                      <input type="checkbox" checked={editRunOnProfile} onChange={e => setEditRunOnProfile(e.target.checked)} className="rounded" />
                      Run on every profile
                    </label>
                    <div className="flex gap-2">
                      <Button type="submit" size="sm" disabled={editSaving}>
                        {editSaving ? <Loader2 className="size-3.5 animate-spin" /> : 'Update'}
                      </Button>
                      <Button type="button" size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                    </div>
                  </form>
                ) : (
                  <div className="px-3 py-2.5 flex flex-col gap-1.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="outline" className={SEVERITY_BADGE_CLASSES[m.severity] || ''}>
                        {m.severity}
                      </Badge>
                      <span className="text-sm font-medium">{m.name}</span>
                      {m.description && <span className="text-xs text-muted-foreground hidden sm:inline">— {m.description}</span>}
                      <div className="ml-auto flex items-center gap-2">
                        {renderLastResult(m)}
                        <button
                          type="button"
                          onClick={() => handleToggle(m)}
                          disabled={togglingId === m.id}
                          className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${m.is_active
                            ? 'border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-600/20'
                            : 'border-stone-500/30 bg-stone-500/10 text-stone-600 dark:text-stone-400 hover:bg-stone-500/20'
                          }`}
                        >
                          {togglingId === m.id ? '…' : m.is_active ? 'active' : 'inactive'}
                        </button>
                        <Button size="sm" variant="ghost" onClick={() => handleRunNow(m)} disabled={runningId === m.id} className="h-7 px-2">
                          {runningId === m.id ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => startEdit(m)} className="h-7 px-2">
                          <Edit3 className="size-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleDelete(m)} disabled={deletingId === m.id} className="h-7 px-2 text-destructive hover:text-destructive">
                          {deletingId === m.id ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                        </Button>
                      </div>
                    </div>
                    {m.last_run_at && (
                      <p className="text-xs text-muted-foreground">Last run: {formatDateTime(m.last_run_at)}</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
    </div>
  )
}

// ── Unified Custom Monitors Panel ────────────────────────────────────────────

function CustomMonitorsPanel({ tableId, sourceId, tableName, hasMonitors, refreshKey, onMonitorSaved }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4 text-primary" />
          Custom monitors
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {/* ── AI Assist section ── */}
        <div className="flex flex-col gap-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">AI recommendations</p>
          <AIMonitorRecommender
            tableId={tableId}
            sourceId={sourceId}
            tableName={tableName}
            hasMonitors={hasMonitors}
            onMonitorSaved={onMonitorSaved}
          />
          <div className="border-t pt-3">
            <NLRuleBuilder
              tableId={tableId}
              tableName={tableName}
              onMonitorSaved={onMonitorSaved}
            />
          </div>
        </div>

        {/* ── Custom SQL section ── */}
        <div className="flex flex-col gap-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground border-t pt-3">Custom SQL monitors</p>
          <CustomMonitors tableId={tableId} refreshKey={refreshKey} />
        </div>
      </CardContent>
    </Card>
  )
}

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
  const [interval, setInterval_] = useState(15000)
  const [customMonitorsRefreshKey, setCustomMonitorsRefreshKey] = useState(0)
  const [columnSearch, setColumnSearch] = useState('')

  const loadData = async () => {
    const [tableResponse, sourcesResponse, profilesResponse, checksResponse, incidentsResponse] = await Promise.all([
      getTable(id),
      getSources(),
      getTableProfiles(id, { limit: 30 }),
      getTableCheckResults(id, { limit: 100 }),
      getIncidents({ table_id: id, limit: 100 }),
    ])
    setTable(tableResponse.data)
    setSources(sourcesResponse.data)
    setProfiles(profilesResponse.data)
    setChecks(checksResponse.data)
    setIncidents(incidentsResponse.data)
    setLoading(false)
  }

  const { isRefreshing, lastRefreshed, refresh } = useAutoRefresh(loadData, interval, { enabled: interval > 0 })

  const handleRun = async () => {
    const clickedAt = new Date()
    setRunning(true)
    try {
      await runTable(id)
      // Poll for completion every 2s
      const poll = setInterval(async () => {
        try {
          const res = await getTableProfiles(id, { limit: 1 })
          const latest = res.data?.[0]
          if (latest && new Date(latest.collected_at) > clickedAt) {
            clearInterval(poll)
            setRunning(false)
            await loadData()
            notify.ok('Profile complete — data updated')
          }
        } catch (_) { /* ignore poll errors */ }
      }, 2000)
      // Safety timeout after 90s
      setTimeout(() => { clearInterval(poll); setRunning(false) }, 90000)
    } catch (_) {
      setRunning(false)
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
            <RefreshBar
              isRefreshing={isRefreshing}
              lastRefreshed={lastRefreshed}
              onRefresh={refresh}
              interval={interval}
              onIntervalChange={setInterval_}
            />
            <HealthBadge status={table.is_active ? 'healthy' : 'paused'} size="lg" />
            <Button type="button" onClick={handleRun} disabled={running}>
              <Play data-icon="inline-start" />
              {running ? 'Profiling…' : 'Run now'}
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
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="text-base">Column metrics</CardTitle>
          {columnRows.length > 0 && (
            <div className="relative">
              <Search className="absolute left-2.5 top-2 size-3.5 text-muted-foreground" />
              <input
                className="h-8 rounded-md border bg-background pl-7 pr-3 text-xs outline-none focus:ring-1 focus:ring-primary w-44"
                placeholder="Filter columns…"
                value={columnSearch}
                onChange={(e) => setColumnSearch(e.target.value)}
              />
            </div>
          )}
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
                  {columnRows
                    .filter(({ name }) => !columnSearch || name.toLowerCase().includes(columnSearch.toLowerCase()))
                    .map(({ name, metric, nullRate }) => (
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
                  {columnRows.filter(({ name }) => !columnSearch || name.toLowerCase().includes(columnSearch.toLowerCase())).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="py-6 text-center text-sm text-muted-foreground">No columns match "{columnSearch}"</TableCell>
                    </TableRow>
                  )}
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

      <AutopilotPanel
        table={table}
        onMonitorSaved={() => setCustomMonitorsRefreshKey((key) => key + 1)}
        onRefreshTable={loadData}
      />

      <BuiltinMonitorsPanel table={table} onSave={loadData} />

      {/* ── Alert Routing ── */}
      <AlertRoutingPanel tableId={id} />

      {/* ── Custom Monitors (AI assist + SQL monitors unified) ── */}
      <CustomMonitorsPanel
        tableId={id}
        sourceId={table.source_id}
        tableName={`${table.schema_name}.${table.table_name}`}
        hasMonitors={checks.length > 0}
        refreshKey={customMonitorsRefreshKey}
        onMonitorSaved={() => setCustomMonitorsRefreshKey((k) => k + 1)}
      />

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
